# Datastore Plugin

The next version of c-lightning (0.10.2?) has a built-in datastore.

Until then, this plugin serves the same purpose, and has the same
interface.  When it detects that you have upgraded, it will place
its datastore into the built-in one and shut down.

The plugin (`datastore.py`) is a bit weird, in that it loads the
*real* plugin if it detects that it is needed.  This is because a
plugin cannot replace an existing command, so it would fail badly when
you finally upgrade.

## Usage

Just add it to your .lightning/config file as
"plugin=/path/to/plugin/datastore.py".

This plugin is usually used by *other* plugins to store and retreive
data.  The commands, briefly, are:

### **datastore** *key* [*string*] [*hex*] [*mode*]

There can only be one entry for each *key*, so prefixing with the
plugin name (e.g. `summary.`) is recommended.

*mode* is one of "must-create" (default, fails it it already exists),
"must-replace" (fails it it doesn't already exist),
"create-or-replace" (never fails), "must-append" (must already exist,
append this to what's already there) or "create-or-append" (append if
anything is there, otherwise create).

### **deldatastore** *key*

The command fails if the *key* isn't present.

### **listdatastore** [*key*]

Fetch data which was stored in the database.

All entries are returned in *key* isn't present; if *key* is present,
zero or one entries are returned.

## Author

Rusty Russell wrote this so he can use it before the next release, and
plugins can start relying on storing data.
