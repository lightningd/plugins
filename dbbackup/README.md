## Summary plugin

This plugin keeps a synchronized backup of c-lightning's (CL) sqlite3 database.
It uses the db_write hook so that every commit (write) to CL's database is first
written to the backup. This allows recovery of any committed-to channel state,
including HTLCs. This plugin does not backup the seed and is not a complete
node-backup.

## Installation

For general plugin installation instructions see the repos main
[README.md](https://github.com/lightningd/plugins/blob/master/README.md#Installation)

## Options:

* `--db-backup-file`: path of the backup file

## Usage

If the given `db-backup-file` doesn't exist yet, it will be created from a
copy of CL's database.

During startup, any existing backup file is checked to match CL's current
database. If that check fails or initialization fails for other reasons, it will
shutdown CL and log `**BROKEN**`. If the plugin fails in writing to the backup
file, it will trigger CL to crash.

The backup file is created with rw permission for the owner, it contains
sensitive information, so be a bit careful. When plugin complains about mismatch
between backup and original db, please investigate what caused it before
recovering.

To recover: shutdown CL and copy the backup to `~/.lighting/lightningd.sqlite3`
File permissions may need to be restored.

## Testing

The tests uses c-lightning's pytest framework. To run the tests, you can
link or copy this repository's `/dbbackup` directory into c-lightning repo's
`/test` directory. Then cd into the c-lighting repo directory and to run
test_dbbackup_* tests, run: `DEVELOPER=1 py.test tests/ -s -v -k test_dbbackup_`
