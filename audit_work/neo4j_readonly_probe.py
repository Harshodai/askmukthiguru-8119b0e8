from neo4j import GraphDatabase
import os

uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
user = os.environ.get("NEO4J_USER", "neo4j")
password = os.environ.get("NEO4J_PASSWORD", "")

driver = GraphDatabase.driver(uri, auth=(user, password))
try:
    with driver.session() as session:
        for label, query in [
            ("nodes", "MATCH (n) RETURN count(n) AS value"),
            ("relationships", "MATCH ()-[r]->() RETURN count(r) AS value"),
            ("labels", "CALL db.labels() YIELD label RETURN collect(label) AS value"),
            ("indexes", "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, state RETURN collect({name:name,type:type,entityType:entityType,labelsOrTypes:labelsOrTypes,properties:properties,state:state}) AS value"),
        ]:
            record = session.run(query).single()
            print(label, record["value"] if record else None)
finally:
    driver.close()
