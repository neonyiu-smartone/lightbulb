from datetime import datetime
from pony.orm import Database, Required, Optional, Set, PrimaryKey

db = Database()


class ServiceNode(db.Entity):
    service_id = PrimaryKey(str)
    service_type = Required(str)
    label = Required(str)
    details = Optional(str)
    metrics = Optional(str)
    relations = Set('ServiceRelation')
    traces = Set('MonitorTrace')


class ServiceRelation(db.Entity):
    id = PrimaryKey(int, auto=True)
    source = Required(ServiceNode)
    target = Required(ServiceNode)
    relation_type = Optional(str)


class MonitorTrace(db.Entity):
    service = Required(ServiceNode)
    timestamp = Required(str)
    code = Required(int)
    message = Optional(str)
    details = Optional(str)  # You can use JSON string if you want to store structured data