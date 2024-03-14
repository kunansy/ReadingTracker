1. 
```sql
ALTER SYSTEM SET wal_level = logical;
```
2. restart
3. 
```sql
CREATE PUBLICATION notes_wal FOR TABLE notes;
```
4. create replica slot
```sql
SELECT pg_create_logical_replication_slot('debezium', 'pgoutput');
```
5. check 
```sql
select * from pg_publication_tables;
select * from pg_catalog.pg_stat_subscription;
```
6. configure debezium
```shell
curl -X POST -sSl -d @debezium.json -D - http://127.0.0.1:8083/connectors/ \
  -H "Accept: application/json" \
  -H "Content-Type: application/json"
```
7. check
```shell
curl -sSl -D - http://127.0.0.1:8083/connectors/pg-connector/status
```
