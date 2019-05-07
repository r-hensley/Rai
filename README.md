# -Rai-
Discord bot for Discord langauge servers (Python).  Some key features: 
- Extensive logging of joins, leaves, bans, deletes, edits, reaction removes, and invites that people use to join a server
- A report room for users to make either anonymous reports to mods or enter a mod report chat room to discuss an issue.  Designed to eliminate the need for private messages completely from mod business.  
- A smart message prune/clear command which takes a message ID as input so you don't have to count messages
- Configurable reaction requirement to enter a server
- Super watchlist for when you have raiders who are repeatedly making accounts and spamming gore/porn/etc.
- A questions module to manage the questions queue of a server.  Mainly, for people who ask hard questions that get swept away in the channel, this module will help them make sure their question eventually gets answered.
- Options module for easy configuration of options
- Unlimited duration timed mutes and bans.
- Stats module for showing most active users in the server and per channel for the last month.

Invite here: https://discordapp.com/oauth2/authorize?client_id=270366726737231884&scope=bot&permissions=3072

Questions to: Ryry013#9234

# Commands
List of commands for Rai bot.

- [General](#general)
- [Admin](#admin-commands)
  - [Setting the mod role](#setting-the-mod-role)
  - [Setting a custom prefix](#setting-a-custom-prefix)
  - [Captcha to enter a server](#captcha-to-enter-a-server)
  - [Clear/prune messages](#clearprune-messages)
  - [Super_watch lists: an anti-raid tool](#super_watch-lists-an-anti-raid-tool)
  - [Invite link/amazingsexdating spam auto-banning](#invite-linkamazingsexdating-spam-auto-banning)
  - [Stats](#stats)
  - [Chinese server only commands](#chinese-server-only)
  - [Spanish server only commands](#spanish-server-only)
  - [Japanese server only commands](#japanese-server-only)
- [Report room](#report-room)
- [Logging](#logging)
- [Questions](#questions)


## General
These are usable by anyone, mostly just for fun or light general utility.
- **`;chlb (#other_channel_name)`** Shows the leaderboard for the current channel (or another channel if you specify one)
- **`;eraser`** Erases the last character of your nickname, supposedly a :pencil:, made in conjunction with ;pencil.  Mostly a joke command
- **`;github`** Shows my github page
- **`;invite`** Gives an invite to invite Rai to your server
- **`;jisho <text>`** Links to a Jisho search of the text you cite.  Useful for people who ask questions that could be answered with a simple jisho search.
- **`;kawaii`** Try it
- **`;lb`** Shows the guild leaderboard.
- **`;nadeko_flip_test`** A command to simulate the Martingale strategy for Nadeko's coin flip gambling module (alias `;nft`)
- **`;ping`** Doesn't actually perform a ping test but still a good test
- **`;pencil`** Adds a :pencil: to the end of your name to signify that you wish to be corrected.  See ;eraser
- **`;punch`** The first command I made with cogs, just a test, try it
- **`;randomWalk`** <number> Generates a random walk plot, try it
- **`;report`** Starts the dialogue in PM for entering the report room (server admins must run the setup command first)
- **`;ryan`** Posts an invite link to this page/my testing server
- **`;u`** Shows your profile information


  
## Admin Commands
The commands in this module are only usable by users with either the `Administrator` privelege in a server, or if they have the mod role set in the next command.  **Most of these commands can be manipulated easier by typing `;options` and using the menu that comes up.**

#### Setting the mod channel
Important messages from the bot will go here.  This channel doesn't have to actually be your mod channel, just in the channel you want important notifications to go, type:
` **`;set_mod_channel`** Sets the current channel as the mod channel

#### Setting the mod role  
- **`;set_mod_role [role name]`** Sets the mod role for the server.  Type the name of the role exactly in [role name].
- **`;set_submod_role [role name]`** If you want to optionally allow a secondary role to be able to mute users, use this.  Otherwise, `;mute` will default to the main mod role.
  
#### Setting a custom prefix
- **`;set_prefix [prefix]`** Sets a custom prefix, for example, `;set_prefix !`
  - **`<prefix>set_prefix reset`** Resets the prefix to `;`
  
#### Ban/Mute
- **`;ban [time] <user> [reason]`** Bans a user for an optional amount of time with an optional reason.  Examples:
  - `;ban @Ryry013` Bans me indefinitely.  
  - `;ban 1d2h @Ryry013` Bans me for 1 day and 2 hours.
  ` `;ban @Ryry013 for being mean` Bans me indefinitely for being mean.
- **`;mute [time] <user>`** Mutes a user from all text and voice chat.  Similar usage to the above `;ban` command.
  
#### Captcha to enter a server
Sets up a requirement to react to a message with a checkmark to enter a server / get a role.  Follow these steps:
1) First, do `;captcha toggle` to setup the module
2) Then, do `;captcha set_channel` in the channel you want to activate it in.
3) Then, do `;captcha set_role <role name>` to set the role you wish to add upon them captchaing.
4) Finally, do `;captcha post_message` to post the message people will react to.
  
#### Clear/prune messages
**`;clear [number of messages] (user) (message_id)`** *(aliases `;purge`, `;prune`)* A clear/prune command with LOTS of different ways to use it.  For a number of messages above 100, the bot will ask for a confirmation before starting the deleting.  

The `user` field can be an ID, nickname, username, or mention.  It will only delete messages from that user.  

The `message_id`, if specified, will start a prune that deletes all messages past the specified message.  See the following examples.

Typical usage:  
- **`;clear 50`** Clears the last 50 messages in the channel  
- **`;clear 50 USER_ID`** In the last 50 messages in the channel, deletes all messages from specified user.  
- **`;clear 50 Ryry013`** You can also search by username/nickname.  This is risky because the bot might find the wrong person.  
- **`;clear 50 USER_ID MESSAGE_ID`** Deletes all messages from a specified user that also fall after the specified message (The bot will delete 50 messages or all messages below the specified message, whichever is *less*)

Special syntax:  
- **`;clear MESSAGE_ID`** A syntax where you only specify a message ID.  It will default to a max of 100 messages at the most, and it will delete all messages from all users past the specified message id.

#### Report room
A feature that allows users to either make an anonymous report to the mods, or enter a special report room to have a conversation with the mods.  This feature was designed to eliminate the need for PMs in moderation.  Further detail will be written later/is written on my testing server.  For now, how to setup:
1) First, type `;report setup` in the channel you want to be the report room. Set the permissions on that channel so that `@everyone` can not view messages nor channel history. 
2) Make sure you have a mod channel set with `;set_mod_channel` and a mod role set with `;set_mod_role`
3) Type `;report` in a channel to test it all out.

Other commands:
- **`;report check_waiting_list`** Checks who is on the waiting list for the report room
- **`;report clear_waiting_list`** Clears the waiting list
- **`;report [USER / ID]`** Pulls a user into the report room if you want to ask them questions about something.  It is recommended to tell the user you will do this before you do it.
- **`;report reset`** If something bugs out with the report room, use this to reset it.  Make sure to also manually reset the permission overrides of the channel for the last user to have been in the room.

⠀
#### Super_watch lists: an anti-raid tool

Super_watch  
*(alias `;sw`, `;superwatch`)*
If you're being raided by someone who is repeatedly making multiple accounts to rejoin and spam, use this on the accounts that you think are the raiders.  
- **`;super_watch add [id/name]`** Adds someone to the watch list.  Every time they send a message anywhere, the bot will make a post notifying the mods.   
- **`;sw remove [id/name]`** Removes someone from the watch list.  
- **`;sw list`** Shows the current list of super-watched people.  
- **`;sw set`** Set the channel you wish the messages to be posted to

Super_voicewatch  
*(aliases `;svw`, `;supervoicewatch`)*
If you've received reports for a user causing problems in voice, use this to notify the mods whenever that user joins voice so you can go listen and hopefully confirm the reports.  
- **`;super_voicewatch`** Sets-up the module/displays help for it.  
- **`;svw add [USER]`** **`;svw remove [USER]`** Adds/removes a user from the list  
- **`;svw list`** Shows a list of all users on the list currently  

#### Invite link/amazingsexdating spam auto-banning
- **`;auto_bans`** Toggles the banning of all users who join and instantly send an invite link, or those that join and spam a link to amazingsexdating.com.  If you use the below welcome messages module too, then the welcome message won't be posted.

#### Welcome messages
Welcome new users when they join the server
- **`;welcome_message`** Toggles the posting of welcome messages, while keeping the rest of the settings the same  
- **`;welcome_message set_message <message>`** Sets the welcome message to whatever you put inside <message> (without <>).  
- **`;welcome_message set_channel`** Sets the channel you send this command in to be the channel that welcome messages are posted into  
- **`;welcome_message show_message`** Shows the currently set welcome message  
  
Formatting variables: Put any of these in the welcome message to have them replaced with the relevant information in the actual welcome.
- `$NAME` → The name of the user (not a mention, just plaintext)
- `$USERMENTION$` → A ping/mention to the user
- `$SERVER$` → The name of the server

#### Stats
Will keep track of the top posters in a server, and also per channel.  Give users their most-talked-in channels.
- **`;stats`** Enable/disable the stats module
- **`;u`** Shows your profile information
- **`;lb`** Shows the guild leaderboard.
- **`;chlb (#other_channel_name)`** Shows the leaderboard for the current channel (or another channel if you specify one)

#### Chinese server only
- **`;hardcore`** Posts a message in that channel with a reaction for people to click to assign hardcore mode to themselves
- **`;hardcore ignore`** Adds or removes a channel from the list of channels ignored by hardcore mode
` **`;post_rules`** Updates the rules according to the Google Doc pinned in the mod channel.

#### Spanish server only
- **`;post_rules`** Updates the rules according to the Google Doc pinned in the mod channel.

#### Japanese server only
- **`;swap`** Swaps the names and positions of JHO and JHO2.  Use this if JHO is particularly active and you want to move the welcome messages to JHO2.  Or as a fun prank to confuse people.
- **`;ultrahardcore on`** *(Japanese server only) (Alias: `;uhc`)* Enters ultra hardcore mode, you must talk to a mod to remove it, which they can do by `;uhc <user/id>`.  
- **`;ultrahardcore [NAME / ID]`** *(alias `;uhc`) *Removes a user from ultra hardcore mode 
- **`;ultrahardcore ignore`** Adds the channel that you send this message in to the whitelist for ignored channels for ultra hardcore mode.
  - **`;uhc list`** Lists the people in ultra hardcore mode.
  - **`;uhc explanation`** Posts an explanation in English about hardcore mode to help explain to other people why you can't speak English if they don't understand your attempts to explain it to them in Japanese
  -- **`;uhc lb`** Shows a leaderboard of who has had UHC for the longest.

## Logging
Part of the admin commands, but deserves it's own section.  

There's a lot of logging that can be done, and the setup for all of them are pretty much all referring to the same code, so they're all the same.

The things you can log are:
- Deleted / edited messages (`;deletes`, `;edits`)
- Joins / leaves (`;welcomes`/`;joins`, `;leaves`)
  - Detection of which invite link a user used to join the server (`;invites`)
  - Readdition of roles to users who have left the server before and rejoin (`;readd_roles`)
- Nickname / username changes (`;nicknames`)
- Deleted reactions (so users can't react an insult and then clear it) (`;reactions`)
- Kicks / bans (`;kicks`, `;bans`)

Each module has a module name listed above in parenthesis (for example, "delete" for deleted messages logging), and can be either singular or plural to work (`;delete` and `;deletes` are the same and both work).

To toggle a module, just type the module name with the command prefix (example: `;deletes`)

To set the channel that the logging gets posted in, type the name of the module, then "set" (example: `;deletes set`)

For examples/screenshots of all the loggings, try it yourself or see my testing server.
⠀
## Questions
This module helps streamline the question asking process.  Mainly, for people who ask hard questions that get swept away in the channel, this module will help them make sure their question eventually gets answered.  

__To setup__  
Go to your questions channel and type `;question setup`.  You should be able to do this for multiple channels.

__To ask your own question__  
`;question <Title for your question>` (alias `;q`)  
The bot will react with a number telling you the `Question ID`.  
Example: `;q What is 2+2?`

__To mark someone else's comment as a question for them__  
`;question <the question's message ID> [optional title]`  
Cite the message ID of the original question
Example: `;q 553582103464378368``

__To mark a question as answered__
`;question answer <Question ID>` (alias `;q a`)  
Type this after enough answers have been given to consider the question answered  
Example: `;q a 1`

__To cite a certain comment as an answer__  
Same as above, but add the message ID to the end.  
`;question answer <Question ID> <Message ID>`  
Example: `;q a 1 553582103464378368`

__Shortcut: To mark your own question as answered__
If you're the person to make the question, you can just type `;q a` when your question has been answered.

__Editing a log__  
`;question edit <log_id> <target: what you want to change> <text>`  
You have the option for target of changing the asker, answerer, question, title, or answer of a question.
 
__Other commands__  
- `;question open <Message ID of message log>` - Reopens a closed question  
- `;question list` - Shows a list of all open questions
- `;question bump <message_id>` Bumps a question in the question log to the bottom of the log channel
