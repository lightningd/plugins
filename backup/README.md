# A simple and reliable backup plugin

**This version only supports the default SQLite3 database**

This plugin will maintain clean database backups to another location. It uses
the `db_write` hook to make sure to always have a backup that isn't missing any
states and be potentially harmful.


## Installation

There are some python dependencies. You can install them using `pip`:

```bash
pip3 install --user -r requirements.txt
```


## Setup

Before using the backup pluging it has to be initialized once. The following
command will create a `backup.lock` file lightning directoy that stores the
internal state and makes sure that not two or more instances are using the same
backup.

```bash
./backup-cli init ~/.lightning/bitcoin file:///mnt/external/location
```

Notes:
 - Make sure to adjust your `~/.lightning/bitcoin` directory to your needs.
 - You should use some non-local SSH or NFS mount as destination.
 - Currently only `file:///` URL scheme is supported.

## IMPORTANT note about hsm_secret

**You need to secure your nodes `~/.lightning/bitcoin/hsm_secret` once! This
file will not change, but without this file, you won't be able to use your
database backup!**

Make sure it has user read only permissions, otherwise `lightningd` will refuse
to work: `chmod 0400 hsm_secret`


## Running

In order to tell `lightningd` to use the plugin you either need to tell it
via the startup option `--plugin /path/to/backup.py` or by placing it (or a
symlink to it) in the lightning dir's plugin directory (`~/.lightning/plugins`).

On daemon startup the plugin will check for the integrity of last prior backup
and complain if theres a mismatch.


## Restoring a backup

If things really messed up and you reinstall clightning on a new host, you can
restore the database backup by using the `backup-cli` utility:

```bash
./backup-cli restore file:///mnt/external/location ~/.lightning/bitcoin/lightningd.sqlite3
```
