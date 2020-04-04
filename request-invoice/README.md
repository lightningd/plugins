 # Http Invoice Request Server plugin


This plugin starts a minimal, rate limited HTTP Server and returns a invoice on the following GET request:

``/invoice/<amount>/<description>``

```
$ lightning-cli invoiceserver
started server successfully on port 8089
$ curl http://localhost:8809/invoice/100000/some-text-here
{"bolt11":"lnbc100000n1p0yr9sxpp50t9rnvw5slcjn6m97fmujpp9xd6w0h26dpvajcv8xwhu42xk5vlqdq8vej8xcgxqyj...","expires_at":1581961350,"payment_hash":"7aca39b1d487f129eb65f277c904253374e7dd5a6859d9618733afcaa8d6a33e", ...}
```

The webserver is rate-limited, meaning that only a certain amount of request per minute is allowed (to prevent DoS attacks).

The json invoice can be used by other services, for example a service for tipping, donations, PoS devices, ...


Once the plugin is active you can run `lightning-cli help invoiceserver` to
learn about the command line API:

Commands: `start`/`stop`/`restart`/`status`.

In the file `.lightning/bitcoin/.env` the `port` can be set (default 8089).

A (reverse)proxy or tunnel should be used in production.
