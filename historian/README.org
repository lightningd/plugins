#+TITLE: historian: Archiving the Lightning Network

* About
The historian plugin aims to provide tools to archive the Lightning
Network gossip messages and to work with the archived messages.

The plugin tails the ~gossip_store~ file used by ~lightningd~ to
persist gossip messages across restarts. The plugin monitors the file
for changes and resumes reading messages whenever there is an
actionable event (append, move, etc). When a new message is detected
it is parsed, extracting the fields necessary to deduplicate them and
then stored in the database. The messages themselves are inserted
verbatim in order to maintain their integrity and ensure signatures
remain valid.

** Install the plugin
There are two ways to install the plugin:

 - Specify the path to ~historian.py~ with the ~--plugin~ or
   ~--important-plugin~ options.
 - Add a symbolic link to ~historian.py~ in one of the directories
   specified as ~--plugin-dir~ or in
   ~$HOME/.lightning/bitcoin/plugins~.

Notice that copying the entire directory into the plugin-dir will
cause errors at startup. This is caused by ~lightningd~ attempting to
start all executables in the plugin-dir, even the ~historian-cli~
which is not a plugin. The errors are not dangerous, just annoying and
may delay startup slightly.

If the plugin starts correctly you should be able to call
~lightning-cli historian-stats~ and see that it is starting to store
messages in the database.

** Command line
The command line tool ~historian-cli~ can be used to manage the
databases, manage backups and manage snapshots:

 - A ~backup~ is a full dump of a range of messages from a database,
   it contains all node announcements and channel updates. Backups can
   be used to reconstruct the network at any time in the past.
 - A ~snapshot~ is a set of messages representing the latest known
   state of a node or a channel, i.e., it omits node announcements and
   channel updates that were later overwritten. Snapshots can be used
   to quickly and efficiently sync a node from a database.

The following commands are available:

 - ~historian-cli db merge [source] [destination]~ iterates through
   messages in ~source~ and adds them to ~destination~ if they are not
   present yet.
   
 - ~historian-cli backup create [destination]~ dump all messages in
   the database into ~destination~
   
 - ~historian-cli backup read [source]~ hex-encode each message and
   print one per line.

 - ~historian-cli snapshot full [destination]~ create a new snapshot
   that includes all non-pruned channels, i.e., start from 2 weeks ago
   and collect channels, updates, and nodes.
   
 - ~historian-cli snapshot incremental [destination] [since]~ create a
   new snapshot that only includes changes since the ~since~ date.
   
 - ~historian-cli snapshot read [source]~ hex-encode each message and
   print one per line.
   
 - ~historian-cli snapshot load [source]~ connect to a lightning node
   over the P2P and inject the messages in the snapshot. Useful to
   catch up a node with changes since the last sync.
   
** File format
The plugin writes all messages into a sqlite3 database in the same
directory as the ~gossip_store~ file. There are three tables, one for
each message type, with the ~raw~ column as the raw message, and a
couple of fields to enable message deduplication.

All files generated and read by the ~historian-cli~ tool have four
bytes of prefix ~GSP\x01~, indicating GSP file version 1, followed by
the messages. Each message is prefix by its size as a ~CompactSize~
integer.

If you just want to iterate through messages in a file, there are the
~historian-cli backup read~ and the ~historian-cli snapshot read~
commands that will print each hex-encoded message on a line to
~stdout~.

* Projects
These projects make use of the historian plugin:

 - [[https://github.com/lnresearch/topology][lnresearch/topology]] uses the backups as dataset to enable research
   on the topological evolution of the network.
