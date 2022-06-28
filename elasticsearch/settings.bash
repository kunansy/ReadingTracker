#!/bin/zsh
curl -XPUT "http://localhost:9200/_cluster/settings" \
 -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster": {
      "routing": {
        "allocation.disk.threshold_enabled": false
      }
    }
  }
}'
curl -X PUT "http://localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "transient": {
    "cluster.routing.allocation.disk.watermark.low": "2gb",
    "cluster.routing.allocation.disk.watermark.high": "1gb",
    "cluster.routing.allocation.disk.watermark.flood_stage": "500mb",
    "cluster.info.update.interval": "1m"
  }
}
'
# TODO: run in before start
#sysctl -w vm.max_map_count=262144

#--ulimit nofile=65535:65535