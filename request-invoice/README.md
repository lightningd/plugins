 # Http Invoice Request Server plugin


This plugin starts a minimal, rate limited HTTP Server and returns a invoice on the following GET request:

```
/invoice/<amount>/<description>

localhost:8809/invoice/100000/some-text-here

{"bolt11":"lnbc100000n1p0yr9sxpp50t9rnvw5slcjn6m97fmujpp9xd6w0h26dpvajcv8xwhu42xk5vlqdq8vej8xcgxqyj...","expires_at":1581961350,"payment_hash":"7aca39b1d487f129eb65f277c904253374e7dd5a6859d9618733afcaa8d6a33e", ...}
```

The webserver is rate-limited, meaning that only a certain amount of request per minute is allowed (to prevent DoS attacks).

The json invoice can be used by other services, for example a service for tipping, donations, ...


Command line options are registered by the plugin and can be used to customize its behavior:

| Command line option    | Description                                                         |
|------------------------|---------------------------------------------------------------------|
| `--donation-autostart` | Should the donation server start automatically? (default: `true`)   |
| `--donation-web-port`  | Which port should the donation server listen to? (default: `8809`) |


Once the plugin is active you can run `lightning-cli help invoiceserver` to
learn about the command line API:

Controls a invoice server with `start`/`stop`/`restart`/`list` on `port`.




