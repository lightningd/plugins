# A simple and reliable backup plugin

**This version only supports the default SQLite3 database**

This plugin will maintain clean database backups to another location. It uses
the `db_write` hook to make sure to always have a backup that is not missing any
state updates and is not potentially harmful.


## Installation

There are some Python dependencies. You can install them using `pip3`:

```bash
pip3 install --user -r requirements.txt
```


## Setup

Before the backup plugin can be used it has to be initialized once. The following
command will create a `backup.lock` in the lightning directory that stores the
internal state, and which makes sure no instances are using the same backup.

```bash
./backup-cli init ~/.lightning/bitcoin file:///mnt/external/location
```

Notes:
 - If you are not using the default lightning directory you'll need to
   change `~/.lightning/bitcoin` in the command line to point to that
   directory instead.
 - You should use some non-local SSH or NFS mount as destination,
   otherwise any failure of the disk may result in both the original
   as well as the backup being corrupted.
 - Currently only the `file:///` URL scheme is supported.

## IMPORTANT note about hsm_secret

**You need to secure `~/.lightning/bitcoin/hsm_secret` once! This
file will not change, but without this file, the database backup will be
unusable!**

Make sure it has user read only permissions, otherwise `lightningd` will refuse
to work: `chmod 0400 hsm_secret`


## Running

In order to tell `lightningd` to use the plugin you either need to tell it
via the startup option `--plugin /path/to/backup.py` or by placing it (or a
symlink to it) in the lightning plugin directory (`~/.lightning/plugins`).

On daemon startup the plugin will check the integrity of the existing backup
and complain if there is a version mismatch.


## Restoring a backup

If things really messed up and you need to reinstall clightning, you can
restore the database backup by using the `backup-cli` utility:

```bash
./backup-cli restore file:///mnt/external/location ~/.lightning/bitcoin/lightningd.sqlite3
```
