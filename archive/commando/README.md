# Commando plugin

Commando has been **included in Core Lightning as first class C plugin**.

It has been actively developed since and has more cool new features added
than listed below.

Checkout latest updates on commando at:
https://docs.corelightning.org/docs/commando &
https://docs.corelightning.org/reference/lightning-commando

------------------------------------------------------------------------------------------------------

# Archived Commando python plugin

This plugin allows other nodes to send your node commands, and allows you
to send them to other nodes.  The nodes must be authorized, and must be
directly connected.

Motto: Reckless?  Try going commando!

## Installation

This plugin requires the runes library; and to use runes requires
datastore support.  You can either use a lightningd version after
0.10.1, or the [datastore plugin](https://github.com/lightningd/plugins/blob/datastore/README.md).

For general plugin installation instructions see the repos main
[README.md](https://github.com/lightningd/plugins/blob/master/README.md#Installation)

## Options and Commands

There are two configuration options, which can be specified multiple
times:

* --commando-reader: a node id which can execute (most) `list` and `get` / `summary` commands
* --commando-writer: a node id which can execute any commands.

You can do this for static access lists, no runes necessary. You would
normally put "commando-writer" (or "commando-reader") lines in your
config file.

For quick testing, you can use this fairly awkward command to start the
plugin dynamically, with a reader by node id:

    lightning-cli plugin subcommand=start plugin=`pwd`/commando.py commando_reader=0266e4598d1d3c415f572a8488830b60f7e744ed9235eb0b1ba93283b315c03518


### Using Commando to Control A Node

Once the node has authorized you can run the `commando` command to send it a
command, like this example which sends a `stop` message to 022d...

	lightning-cli commando 022d223620a359a47ff7f7ac447c85c46c923da53389221a0054c11c1e3ca31d59 stop

For more advanced authorization, you can create **runes** which permit
restricted access, and send them along with commands.


### Creating Runes

If you have datastore support (see the [datastore
plugin](https://github.com/lightningd/plugins/blob/datastore/README.md),
you can also create a "rune": anyone who has the rune can use it to
execute the commands it allows.

- `commando-rune` by itself gives a "full access" rune.
- `commando-rune restrictions=readonly` gives a rune which is restricted to get,
  list and summary commands.

For example, say we have peer
0336efaa22b8ba77ae721a25d589e1c5f2486073dd2f041add32a23316150e8b62,
and we want to allow peer
0266e4598d1d3c415f572a8488830b60f7e744ed9235eb0b1ba93283b315c03518 to
run read-only commands:

    0336...$ lightning-cli commando-rune restrictions=readonly
	{
       "rune": "ZN7IkVe8S0fO7htvQ23mCMQ-QGzFTvn0OZPqucp881Vjb21tYW5kXmxpc3R8Y29tbWFuZF5nZXR8Y29tbWFuZD1zdW1tYXJ5JmNvbW1hbmQvZ2V0c2hhcmVkc2VjcmV0"
    }

We could hand that rune out to anyone, to access.

### Using Runes

You use a rune a peer gives you with the `rune` parameter to `commando`, eg:

	02be...$ lightning-cli commando 0336efaa22b8ba77ae721a25d589e1c5f2486073dd2f041add32a23316150e8b62 listchannels {} j2fEW43Y8Ie7d0oGt9pPxaIcl6RP6MjRGC1mgxKuUDxpZD0wMmJlODVlNzA4MjFlNmNjZjIxNDlmMWE3YmY1ZTM0ZDc3OTAwMGY3MjgxNTQ1MDhjYzkwNzJlNGU5MDE4MmNkZDI=

Or, using keyword parameters:

    02be...$ lightning-cli commando peer_id=0336efaa22b8ba77ae721a25d589e1c5f2486073dd2f041add32a23316150e8b62 method=listchannels rune=j2fEW43Y8Ie7d0oGt9pPxaIcl6RP6MjRGC1mgxKuUDxpZD0wMmJlODVlNzA4MjFlNmNjZjIxNDlmMWE3YmY1ZTM0ZDc3OTAwMGY3MjgxNTQ1MDhjYzkwNzJlNGU5MDE4MmNkZDI=

It's more common to set your peer to persistently cache the rune as the default for whenever you issue a command, using `commando-cacherune`:

    02be...$ lightning-cli commando 0336efaa22b8ba77ae721a25d589e1c5f2486073dd2f041add32a23316150e8b62 commando-cacherune {} j2fEW43Y8Ie7d0oGt9pPxaIcl6RP6MjRGC1mgxKuUDxpZD0wMmJlODVlNzA4MjFlNmNjZjIxNDlmMWE3YmY1ZTM0ZDc3OTAwMGY3MjgxNTQ1MDhjYzkwNzJlNGU5MDE4MmNkZDI=
    02be...$ lightning-cli commando 0336efaa22b8ba77ae721a25d589e1c5f2486073dd2f041add32a23316150e8b62 listpeers


### Restricting Runes

There's a [runes library](https://github.com/rustyrussell/runes/): which lets you add restrictions, but for
convenience the  `commando-rune` can also add them, like so:

- `commandorune RUNE RESTRICTION...` 

Each RESTRICTION is a string: fieldname, followed by a condition, followed by a
value.  It can either be a single string, or an array of strings.

Valid fieldnames are:
* **id**: what peer is allowed to use it.
* **time**: time in seconds since 1970, as returned by `date +%s` or Python `int(time.time())`.
* **version**: what version of c-lightning is running.
* **command**: the command they are trying to run (e.g. "listpeers")
* **parr0**..**parrN**: the parameters if specified using a JSON array
* **pnameNAME**..: the parameters (by name) if specified using a JSON object ('-' and other punctuation are removed from NAME).

conditions are listed in the [runes documentation](https://github.com/rustyrussell/runes/blob/v0.3.1/README.md#rune-language):

* `!`: Pass if field is missing (value ignored)
* `=`: Pass if exists and exactly equals
* `^`: Pass if exists and begins with
* `$`: Pass if exists and ends with
* `~`: Pass if exists and contains
* `<`: Pass if exists, is a valid decimal (may be signed), and numerically less than
* `>`: Pass if exists, is a valid decimal (may be signed), and numerically greater than
* `}`: Pass if exists and lexicograpically greater than (or longer)
* `{`: Pass if exists and lexicograpically less than (or shorter)
* `#`: Always pass: no condition, this is a comment.

Say we have peer
0336efaa22b8ba77ae721a25d589e1c5f2486073dd2f041add32a23316150e8b62,
and we want to allow peer
0266e4598d1d3c415f572a8488830b60f7e744ed9235eb0b1ba93283b315c03518 to
run listpeers on itself.  This is actually three restrictions:

1. id=0266e4598d1d3c415f572a8488830b60f7e744ed9235eb0b1ba93283b315c03518,
   since it must be the one initiating the command.
2. method=listpeers, since that's the only command it can run.
3. pnameid=0266e4598d1d3c415f572a8488830b60f7e744ed9235eb0b1ba93283b315c03518 OR
   parr0=0266e4598d1d3c415f572a8488830b60f7e744ed9235eb0b1ba93283b315c03518;
   we let them specify parameters by name or array, so allow both.
   
We can add these restrictions one at a time, or specify them all at
once.  By default, we start with the master rune, which has no
restrictions:

    0336...$ lightning-cli commando-rune restrictions='["id=02be85e70821e6ccf2149f1a7bf5e34d779000f728154508cc9072e4e90182cdd2","method=listpeers","pnameid=0266e4598d1d3c415f572a8488830b60f7e744ed9235eb0b1ba93283b315c03518|parr0=0266e4598d1d3c415f572a8488830b60f7e744ed9235eb0b1ba93283b315c03518"]'
	{
       "rune": "-As0gqymadZpgTnm9fBoDVtrjPmpwPrKmCQWUcqlouJpZD0wMmJlODVlNzA4MjFlNmNjZjIxNDlmMWE3YmY1ZTM0ZDc3OTAwMGY3MjgxNTQ1MDhjYzkwNzJlNGU5MDE4MmNkZDImbWV0aG9kPWxpc3RwZWVycyZwbmFtZWlkPTAyNjZlNDU5OGQxZDNjNDE1ZjU3MmE4NDg4ODMwYjYwZjdlNzQ0ZWQ5MjM1ZWIwYjFiYTkzMjgzYjMxNWMwMzUxOHxwYXJyMD0wMjY2ZTQ1OThkMWQzYzQxNWY1NzJhODQ4ODgzMGI2MGY3ZTc0NGVkOTIzNWViMGIxYmE5MzI4M2IzMTVjMDM1MTg="
    }

We can publish this on Twitter and it doesn't matter, since it only
works for that one peer.


### Temporary Runes to Authorize Yourself

This creates a rune which can only be used to create another rune for
a specific nodeid, for (as of this writing!) the next 60 seconds:

	lightning-cli commando-rune restrictions='["method=commando-rune","pnamerestrictions^id=|parr1^id=","time<1627886935"]'

That rune only allows them to rune "commando-rune" with an "id="
restriction, within the given time; useful to place in a QR code to
allow self-authorization.


### Huge Commands and Responses

Commands larger than about 64k are split into multiple parts; command
responses similarly.  To avoid a Denial of Service, commands must be
less than about 1MB in size: that's increased to 10MB if the peer has
successfully used `commando-cacherune`.
