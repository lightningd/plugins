# Autoreload Plugin

> You write the code, we do the rest!

The autoreload plugin aims to help plugin developers to reload the plugin
inside of `lightningd` without having to restart the entire daemon. It watches
the executable file and will restart the plugin when a change is detected.

The plugin adds the following command line options:

 - `--autoreload-plugin=path/to/plugin.py`: specifies which plugin you'd like
   `autoreload` to manage. The syntax was chosen so you can just prefix any
   existing `--plugin` with `autoreload` and start hacking.
   
The plugin adds the following RPC methods:

 - `autoreload-restart`: triggers a manual restart of the plugin under
   development, useful if you want to reload because of a dependency change or
   you have a script that knows when a reload is needed. We will still
   autoreload whenever we detect a change in the executable.


So in order to have a plugin `path/to/plugin.py` autoreload on changes you'll
need to call `lightningd` with the following arguments:

```bash
lightningd --plugin=path/to/autoreload.py --autoreload-plugin=path/to/plugin.py
```

The first argument loads the `autoreload` plugin, and the second argument
tells `autoreload` to load, watch and restart the plugin under development.

## Install

This plugin relies on the `pylightning` and the `psutil` libraries. You should
be able to install these dependencies with `pip`:

```bash
pip3 install -r requirements.txt
```

You might need to also specify the `--user` command line flag depending on
your environment.

## How does it work?

In order to hide the restarts from `lightningd` the autoreload plugin will
insert itself between `lightningd` and the plugin that is to be reloaded,
acting as an almost transparent proxy between the two. The only exception to
this are the two calls to register and initialize the plugin:

 - `getmanifest` is captured and the autoreload RPC methods and options are
   injected, so `lightningd` knows about them and tells us when we get
   initialized.
 - `init` is captured and the options we returned above are stripped again,
   otherwise we might upset the plugin under development. We also cache it, so
   we can tell the plugin under development again when we restart it.

Upon restarting we call `getmanifest` on the plugin under development just to
be safe (though you wouldn't do any initialization before being told so with
`init` would you? :wink:) and we then call `init` with the parameters we
cached when we were initialized ourselves. After this initialization dance is
complete, we will simply forward any calls directly to the plugin under
development and forward any output it produces to `lightningd`.

We watch the modification time of the executable file and automatically
restart the plugin should it change. You can trigger this by changing the file
or even just `touch`ing it on the filesystem. You can also trigger a manual
restart using the `autoreload-restart` RPC method:

```bash
lightning-cli autoreload-restart
```

## Caveats :construction:

 - Only one plugin can currently be managed by the autoreload plugin.
 - Log lines will be prefixed with the autoreload plugin's name, not the
   plugin under development.
 - Since the registration of options, subscriptions, methods and hooks happens
   during startup in `lightningd` you cannot currently add or remove any of
   these without restarting `lightningd` itself. If you change them and have
   autoreload restart the plugin under development you might experience
   strange results.
 
