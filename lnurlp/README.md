# HTTP lnurlp plugin

This plugin starts a minimal, rate limited HTTP server which returns an invoice on the following GET request:

`/payRequest?amount=...`

```
$ curl http://localhost:8806/payRequest?amount=123123
{"pr":"lnbc123123...","routes":[]}
```

The webserver is rate-limited, meaning that only a certain amount of request per minute per IP address is allowed, to mitigate DoS attacks.

## lnurl payment flow

The overall flow is documented in [LUD-06](https://github.com/fiatjaf/lnurl-rfc/blob/luds/06.md).

Paying to static internet identifiers (the main use case) is described in [LUD-16](https://github.com/fiatjaf/lnurl-rfc/blob/luds/16.md). Basically, the `https://<domain>/.well-known/lnurlp/<username>` should return a JSON structure like:

```javascript
{
    "status": "OK",
    "callback": "https://domain.tld/path/to/payRequest",
    "maxSendable": 100000000000,
    "minSendable": 1000,
    "commentAllowed": 0,
    "metadata":"[[\"text/identifier\",\"user@domain.tld\"],[\"text/plain\",\"Donation to user@domain.tld.\"]]",
    "tag": "payRequest"
}
```

The callback URL `https://domain.tld/path/to/payRequest` is what is implemented by this plugin, generally it is reverse-proxied in the web server configuration to add TLS
(or over Tor, see below). Exposing the HTTP port directly is not advised as it makes Man-in-the-Middle attacks trivial.

It is important for value of the field `metadata` to be in sync between the web server and lightning plugin. This because a SHA256 hash of it is committed to in the `description_hash` of the returned invoice.

## Reverse proxy in Nginx

To set up the reverse proxy in Nginx put something like this under the `server` directive:

```
  location /payRequest {
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header Proxy "";

    proxy_pass http://127.0.0.1:8806/payRequest;
    proxy_http_version 1.1;
  }
```

Setting `X-Forwarded-For` and `X-Forwarded-Proto` headers is important to make sure that the end-user IP address is used for rate limiting, not localhost.

## Tor onion service

Exposing the URL using Onion routing is easy. Install Tor and add the service to `/etc/tor/torrc`

```
HiddenServiceDir /home/bitcoin/tor/lnurlp_service/
HiddenServicePort 80 127.0.0.1:8806
```

and restart tor to create the URL:

```
$ systemctl stop tor && systemctl start tor
$ cat /home/bitcoin/tor/lnurlp_service/hostname
fkfuvjrbj...onion
```

Use Tor browser to visit the URL to test: `http://fkfuvjrbj...onion/payRequest?amount=...`.

## Reverse-proxy over Tor

Web servers generally don't support reverse-proxing over SOCKS (at least Nginx doesn't, at this time). To set this up, it can be useful to run `socat` as a bridge service.

One way to do this is to create a file `/etc/systemd/system/http-to-socks-proxy@.service`:

```
[Unit]
Description=HTTP-to-SOCKS proxy. Enables placing an HTTP proxy (e.g., nginx) in front of a SOCKS proxy (e.g., Tor).
After=network.target

[Service]
EnvironmentFile=/etc/http-to-socks-proxy/%i.conf
ExecStart=/usr/bin/socat tcp4-LISTEN:${LOCAL_PORT},reuseaddr,fork,keepalive,bind=127.0.0.1 SOCKS4A:${PROXY_HOST}:${REMOTE_HOST}:${REMOTE_PORT},socksport=${PROXY_PORT}

[Install]
WantedBy=multi-user.target
```

And `/etc/http-to-socks-proxy/lnurlp.conf`:

```
PROXY_HOST=127.0.0.1
PROXY_PORT=9050
LOCAL_PORT=8806
REMOTE_HOST=fkfuvjrbj...onion
REMOTE_PORT=8806
```

On the command line:

```
ln -s /etc/systemd/system/http-to-socks-proxy\@.service /etc/systemd/system/multi-user.target.wants/http-to-socks-proxy\@lnurlp.service
systemctl daemon-reload
systemctl start http-to-socks-proxy@lnurlp.service
systemctl status http-to-socks-proxy@lnurlp.service
```

This will forward `http://127.0.0.1:8806` to the onion service over Tor. Reverse-proxying is otherwise the same.

## Configuration

The only necessary configuration is the path to the endpoint JSON file (e.g. `/home/www/host/.well-known/lnurlp/jsonfile`) for the `metadata`
field:

- `--lnurlp-meta-path=...`

(optional) You can make the plugin use a specific port and address:

- `--lnurlp-address=... (default 127.0.0.1)`
- `--lnurlp-port=... (default 8806)`

(optional) You can set the rate of the rate limiter, or disable it:

Rate limits are specified as strings following the format:
```
[count] [per|/] [n (optional)] [second|minute|hour|day|month|year]
```

You can combine multiple rate limits by separating them with a delimiter of your choice.

e.g.:

- `--lnurlp-ratelimit="1 per minute"`
- `--lnurlp-ratelimit="10/hour"`
- `--lnurlp-ratelimit="2 per 2 minutes;3 per hour;42 per day"`
- `--lnurlp-ratelimit="100/day, 500/2months"`

Default is "2 per minute".

To disable rate limiting:

- `--lnurlp-ratelimit="disable"`
