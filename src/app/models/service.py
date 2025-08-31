from typing import Literal, Optional
from src.app.data.service import DataService
from src.app.datasets.service import DatasetsService
from src.app.users.service import UsersService
from src.app.models.dao import ModelsDao
from pymongo.database import Database
from bson.objectid import ObjectId
from src.app.configurations.service import ConfigurationsService
from src.helpers.base_service import BaseService
from src.helpers import utils
import copy, random, uuid, re, time

class ModelsService(BaseService):
    
    def __init__(self, db: Database) -> None:
        super().__init__(db)
        self.dao = ModelsDao(db)

        self.configurations_service = ConfigurationsService(db)
        self.data_service = DataService(db)
        self.datasets_service = DatasetsService(db)
        self.user_service = UsersService(db)

    def find_all(self):
        models = self.dao.find_all()
        for model in models:
            model["created_by"] = self.user_service.dao.find_one({
                "_id": ObjectId(model["created_by"])
            }, 
            projection={
                "password": 0,
                "apikey": 0,
                "role": 0
            }) if model.get("created_by") else None
        return models

    def create(self, user_id: str, model_data: dict) -> ObjectId:
        doc = {
            "name": model_data.get("name", "Untitled Model"),
            "description": model_data.get("description", ""),
            "reference": model_data.get("reference", ""),
            "version": model_data.get("version", "1.0"),
            "configuration": ObjectId(model_data.get("configuration", None)),
            "randomizers": model_data.get("randomizers", []),
            "mapper": model_data.get("mapper", {}),
            "entities": model_data.get("entities", {}),
            "labels": self.build_model_labels(model_data.get("entities", {})),
            "created_by": ObjectId(user_id),
            "created_at": utils.get_current_time(),
        }

        self.dao.col.insert_one(doc)

        return self.dao.serialize(doc)

    def build_model_labels(
        self,
        entities: dict
    ) -> list[str]:
        labels = ["O"]

        for ent in entities.keys():
            labels.append(f"B-{ent}")
            labels.append(f"I-{ent}")
        
        return labels

    def build_model(self, model_id: str, size: str, *, user_id: str = None) -> dict:
        model = self.get_document(id=model_id)

        mversion = model.get("version", "1.0")
        ments = model.get("entities", {})
        mkeys = list(ments.values())

        mcid = model.get("configuration", None)
        if not mcid:
            raise ValueError("Model configuration is missing")

        configuration = self.configurations_service.get_document(id=mcid)

        dataset = []

        n_max = configuration.get("possibilities", 1e5)
        n_size = size.get("size", n_max)
        if utils.is_integer(n_size):
            n_size = int(n_size)
        else:
            n_size = self.model_build_calculate_size(n_size, n_max, len(configuration.get("formats", [])))

        print(user_id)

        docdt = {
            "model": ObjectId(model_id),
            "version": mversion,
            "size": size,
            "created_at": utils.get_current_time(),
            "status": "generating",
            "created_by": ObjectId(user_id) if user_id else None
        }

        docdtid = self.datasets_service.dao.insert_one(docdt)["_id"]

        for _ in range(n_size):
            mvb = self.build_model_configuration(copy.deepcopy(configuration))

            try:
                mrd = random.choice(model.get("randomizers", []))
                rdm = self.build_model_configuration_randomizers(mrd)
                mvb["format"] = rdm(mvb["format"])
            except: pass
            
            dataset.append(
                self.build_model_entity(
                    mvb,
                    mkeys,
                    {v:k for k,v in ments.items()}
                )
            )

            time.sleep(1e-9)

        for data in dataset:
            self.datasets_service.add_data(docdtid, data)

        self.datasets_service.update_status(docdtid, "generated")

        self.dao.update_one(
            {"_id": ObjectId(model_id)},
            { "version": utils.bump_version(mversion, "minor"), "updated_at": utils.get_current_time()}
        )

        return self.model_build_example(dataset, ments, examples_size=3)

    def model_build_calculate_size(
            self,
            size: str,
            max_size: int,
            formats_size: int
        ) -> int:
        match size:
            case "complete":
                return max_size
            case "advanced":
                return max_size // 2
            case "recommended":
                return max_size // formats_size
            case "small":
                return max_size // formats_size // 2
            case "tiny":
                return max_size // formats_size // 5
            case _:
                return int(1e3)

    def build_model_configuration(self, configuration: dict) -> dict:
        catt = configuration.get("attributes")
        cfmt = configuration.get("formats")

        sfmt = random.choice(cfmt)
        satt = []

        for attr in catt:
            kattr = attr.get("key")
            fattr = attr.get("frequency", 1)
            rattr = attr.get("requirements", [])

            vattr = attr.get("value") if fattr > random.random() else False

            if isinstance(vattr, dict):
                tvattr = vattr.get("type")
                rvattr = vattr.get("rule")
                pvattr = vattr.get("parameters", {})
                bvattr, bcattrs = self.build_model_configuration_value(tvattr, rvattr, pvattr)

                if bcattrs:
                    for bcattr in bcattrs:
                        satt.append(bcattr)
            
            satt.append({
                "key": kattr,
                "value": bvattr if vattr else '',
                "requirements": self.build_model_configuration_requirements(bvattr, rattr) if vattr else True
            })

        bfmt = self.build_model_configuration_format(sfmt, satt)
        configuration['attributes'] = satt
        configuration['format'] = re.sub(r'\s+', ' ', bfmt.strip())

        return configuration

    def build_model_configuration_value(
        self,
        vtype: Literal["number", "string"],
        rule: str,
        parameters: dict
    ) -> Optional[int | str]:
        value = None

        match rule:
            case "randint":
                vmin = int(parameters.get("min", 0))
                vmax = int(parameters.get("max", 100))
                if vmin > vmax: vmin, vmax = vmax, vmin
                value = random.randint(vmin, vmax)

            case "data":
                data_id = parameters.get("object_id")
                if data_id:
                    data = self.data_service.get_document(id=data_id)
                    value = random.choice(data.get("data", []))

            case "configuration":
                config_id = parameters.get("object_id")
                if config_id:
                    config = self.configurations_service.get_document(id=config_id)
                    value = self.build_model_configuration(config.get("configuration", {}))
        
        if value is None: return None, None
            
        return self.build_model_configuration_vtype(vtype, value), None
    
    def build_model_configuration_vtype(
        self,
        vtype: Literal["number", "string"],
        value: any
    ) -> Optional[int | str]:
        match vtype:
            case "number":
                try:
                    return int(value)
                except:
                    return str(value)
            case _:
                return str(value)

    def build_model_configuration_requirements(
        self,
        value: any,
        requirements: list[dict]
    ) -> bool:
        for req in requirements:
            rreq = req.get("rule")
            creq = req.get("constraint")

            match rreq:
                case "regex":
                    if not re.match(creq, str(value)):
                        return False
                case "eq":
                    if str(value) != str(creq):
                        return False
                case "neq":
                    if str(value) == str(creq):
                        return False
                case "gt":
                    try:
                        if float(value) <= float(creq):
                            return False
                    except: pass
                case "lt":
                    try:
                        if float(value) >= float(creq):
                            return False
                    except: pass
                case "gte":
                    try:
                        if float(value) < float(creq):
                            return False
                    except: pass
                case "lte":
                    try:
                        if float(value) > float(creq):
                            return False
                    except: pass
                case "in":
                    if str(value) not in map(str, creq):
                        return False
                case "nin":
                    if str(value) in map(str, creq):
                        return False
                case _:
                    pass
                    
        return True

    def build_model_configuration_format(
        self,
        format: str,
        attributes: list[dict]
    ) -> str:
        for attr in attributes:
            kattr = attr.get("key")
            vattr = attr.get("value", "")
            format = format.replace(f"{{{kattr}}}", str(vattr))
        return format
    
    def build_model_configuration_randomizers(
        self,
        randomizer:  str
    ) -> lambda x: x:
        rrand = randomizer.get("rule")
        frand = randomizer.get("frequency", 1)

        f = None

        match rrand:
            case "upper":
                f = lambda x: x.upper()
            case "lower":
                f = lambda x: x.lower()
            case _:
                f = lambda x: x

        return f if frand >= random.random() else lambda x: x

    def build_model_entity(
        self,
        configuration: dict,
        keys: list[str],
        map: dict
    ) -> dict:
        vfmt = configuration.get("format", "")
        ents = []

        for attr in configuration.get("attributes", []):
            kattr = attr.get("key")
            vattr = attr.get("value", "")
            rattr = attr.get("requirements", True)


            if not kattr in keys or \
               vattr == '' or not rattr:
                continue

            enttok = map.get(kattr)

            strvattr = str(vattr)
            sta = vfmt.lower().find(strvattr.lower()) if vattr else -1
            if sta == -1: continue
            end = sta + len(strvattr)

            ents.append([sta, end, enttok])
        
        return { "text": vfmt, "entities": ents }
    
    def model_build_example(
        self,
        dataset: list[dict],
        entities: list[str],
        *,
        examples_size: int = 3
    ) -> list[dict]:
        dataset = dataset[0:examples_size] if len(dataset) >= examples_size else dataset
        res = []

        for data in dataset:
            dtext = data.get("text", "")
            dents = data.get("entities", [])
            rents = []

            for ent in dents:
                sta, end, enttok = ent
                vent = dtext[sta:end]
                vtok = entities[enttok]

                rents.append({ "key": vtok, "value": vent })
            
            res.append({
                "text": dtext,
                "entities": rents
            })

        return res