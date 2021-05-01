## Create certificate
```shell
openssl req -x509 -out localhost.crt -keyout localhost.key \
  -newkey rsa:4096 -nodes -sha256 \
  -subj '/CN=localhost' -extensions EXT -config <( \
   printf "[dn]\nCN=localhost\n[req]\ndistinguished_name = dn\n[EXT]\nsubjectAltName=DNS:localhost\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth")
```

## Nginx config
```
server {
    listen       tracker.localhost:80;
    server_name  tracker.localhost;

    return 301 https://$host$request_uri;
}

server {
	listen 443 ssl http2;

    server_name         localhost default_server;
    keepalive_timeout   60;

    ssl_certificate     /home/kirill/programming/Python/PythonProjects/ReadingTracker/localhost.crt;
    ssl_certificate_key /home/kirill/programming/Python/PythonProjects/ReadingTracker/localhost.key;
    ssl_protocols       TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8080;
        include proxy_params;
    }
}
```
