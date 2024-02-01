Remote backup backend for Core-Lightning
=====================================

Introduction
------------

The purpose of this backend is to allow hassle-free incremental remote backups of a Core-Lightning
daemon's state.

The remote backup system consists of two parts:

- A `backup.py` plugin backend that listens for changes to Core-Lightning's database and communicates them 
  to a remote server.

- A server daemon that receives changes from the backup backend and communicates with a local backup backend
  to store them. The server side does not need to be running Core-Lightning, nor have it installed.

### URL scheme

The backend URL format is `socket:<host>:<port>[?<param>=<value>[&...]]`. For example `socket:127.0.0.1:1234`. To supply a IPv6
address use the bracketed syntax `socket:[::1]:1234`.

The only currently accepted `<param>` is `proxy`. This can be used to connect to the backup server through a proxy. See [Usage with Tor](#usage-with-tor).

Usage
-----

First initialize an empty file backend on the server side, then start the server:

```bash
backup-cli init file:///path/to/backup
backup-cli server file:///path/to/backup 127.0.0.1:8700
```

On the client side:

```bash
# Make sure Core-Lightning is not running
lightning-cli stop
# Initialize the socket backend (this makes an initial snapshot, and creates a configuration file for the plugin)
backup-cli init socket:127.0.0.1:8700 --lightning-dir "$HOME/.lightning/bitcoin"
# Start c-lighting, with the backup plugin as important plugin so that any issue with it stops the daemon
lightningd ... \
    --important-plugin /path/to/plugins/backup/backup.py
```

Usage with SSH
--------------

The easiest way to connect the server and client if they are not running on the same host is with a ssh
forward. For example, when connecting from another machine to the one running Core-Lightning use:

```bash
ssh mylightninghost -R 8700:127.0.0.1:8700
```

Or when it is the other way around:

```bash
ssh backupserver -L 8700:127.0.0.1:8700
```

Usage with Tor
--------------

To use the backup plugin with Tor the Python module PySocks needs to be installed (`pip install --user pysocks`).

Assuming Tor's `SocksPort` is 9050, the following URL can be used to connect the backup plugin to a backup server over an onion service:

```
socket:axz53......onion:8700?proxy=socks5:127.0.0.1:9050
```

On the server side, manually define an onion service in `torrc` that forwards incoming connections to the local port, e.g.:

```
HiddenServiceDir /var/lib/tor/lightning/
HiddenServiceVersion 3
HiddenServicePort 8700 127.0.0.1:8700
```

Goals
-----

- Hassle-free incremental remote backup of Core-Lightning's database over a simple TCP protocol.

- Safety. Core-Lightning will only proceed when the remote backend has acknowledged storing a change, and will halt when there is no connection to the backup server.

- Bandwidth efficiency. Updates can be really large, and SQL statements ought to be well compressible, so bandwidth is saved by performing zlib compression on the changes and snapshots. 

Non-goals
---------

- Encryption. This is outside scope, a VPN (say, a wireguard connection), SSH tunnel (ssh `-L` or `-R`), or even a Tor onion service is more flexible, avoids the pitfalls of custom cryptography code, and for the user to learn yet another way to configure secure transport.

Protocol details
================

A bidirectional TCP protocol is used to synchronize state between the client and server. It is documented here in case anyone wants to make a custom server implementation.

Packet format:

    <typ u8> <length u32> <payload u8 * length...>

Every packet has a type and a 32-bit length. Defined packet types are:

    0x01 CHANGE        Change
    0x02 SNAPSHOT      Snapshot
    0x03 REWIND        Rewind a version (can only be done once)
    0x04 REQ_METADATA  Request metadata
    0x05 RESTORE       Request stream of changes to restore
    0x06 ACK           Acknowledge change, snapshot or rewind
    0x07 NACK          An error happened (e.g. rewind too far)
    0x08 METADATA      Metadata response
    0x09 DONE          Restore is complete
    0x0A COMPACT       Do backup compaction
    0x0B COMPACT_RES   Database compaction result

CHANGE
------

A database update.

Fields:

- version (u32)
- a list of SQL statements to be executed for this update, encoded as UTF-8, separated by NULL bytes. The last statement will not be terminated with a NULL byte. (zlib compressed)

SNAPSHOT
--------

A full database snapshot, replacing the previous incremental backup.

Fields:

- version (u32)
- a raw dump of the sqlite database (zlib compressed)

REQ_METADATA
------------

Request metadata from server. The server should respond with a `METADATA` packet.

No fields.

RESTORE
-------

Request a stream of changes to restore the database.

The server should respond with a stream of `CHANGE` and `SNAPSHOT` packets, finishing with a `DONE` packet.

Unlike when sending a change to backup, the client is not required to (but may) respond to these with `ACK`.

No fields.

ACK
---

General succss response. Acknowledge having processed a `CHANGE` and `SNAPSHOT` packet.

Fields:

- new version (u32)

NACK
----

Indicates an error processing the last packet.

No fields.

METADATA
--------

Metadata response, sent as response to `REQ_METADATA`.

Fields:

- protocol (should be 0x01) (u32)
- version (u32) 
- prev_version (u32)
- version_count (u64)

COMPACT
--------

Do a database compaction. Sends `COMPACT_RES` on succesful completion, `NACK` otherwise.

COMPACT_RES
-----------

Result of a database compaction.

Fields

- A UTF-8 encoded JSON data structure with statistics as returned by Backend.compact()
