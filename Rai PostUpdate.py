# These are the dependecies. The bot depends on these to function, hence the name. Please do not change these unless
# your adding to them, because they can break the bot.
import discord
import asyncio
from discord.ext.commands import Bot
import os

dir_path = os.path.dirname(os.path.realpath(__file__))

# Here you can modify the bot's prefix and description and whether it sends help in direct messages or not.
client = Bot(description="Basic Bot by Ryry013#9234", command_prefix="r!", pm_help=False, owner_id=202995638860906496)


@client.event
async def on_ready():
    client.germanicServListChan = client.get_channel(413491181171900416)

    client.hubServListChan = client.get_channel(250884951535255553)
    client.hubServMobileChan = client.get_channel(368564776386953226)
    client.mass_languages = client.get_channel(539027513855180800)
    client.romance_langauges = client.get_channel(539027646185472010)
    client.germanic_languages = client.get_channel(539027735478140928)
    client.east_asian_languages = client.get_channel(539027799323967508)
    client.balto_slavic_languages = client.get_channel(539027864885133312)
    client.other_languages = client.get_channel(539027949085786113)

    client.modServListChan = client.get_channel(258312052936802304)
    client.modServMobileChan = client.get_channel(367494244270866435)

    client.spanServ = client.get_guild(243838819743432704)

    to_delete_channels = [
        client.modServListChan,
        client.mass_languages,
        client.romance_langauges,
        client.germanic_languages,
        client.east_asian_languages,
        client.balto_slavic_languages,
        client.other_languages,
        client.germanicServListChan,
    ]

    print(to_delete_channels)

    only_reddit = False

    print('Updating posts')

    def is_me(m):
        return m.author == client.owner_id or m.author == client.user

    """Reading files"""
    listFull = []
    listMob = []
    print('Reading files')
    for i in range(4):  # Reads the list files
        with open(f'{dir_path}/list{i}.txt', 'r', encoding='utf-8') as read_file:
            file_text = read_file.read()
        listMob = listMob + file_text.replace('##', '').replace('app.com/invite', '.gg').split('\n')
        listFullLen = len(listFull)
        listFull += file_text.split('##')
        #  list full format is as follows:
        #  [ channel 1 ID, channel 1 text, channel 2 ID, channel 2 text, ...]

    if not only_reddit:
        """Deleting previous messages"""
        print("Starting deleting of messages")
        for channel in to_delete_channels:
            delete_iterator = 0
            try:
                await channel.purge(limit=200, check=is_me)
            except asyncio.queues.QueueEmpty:
                pass
            except discord.errors.Forbidden:
                pass
            except AttributeError:
                print(channel)
                continue
            async for message in channel.history():
                if is_me(message):
                    delete_iterator += 1
                    print(f"Deleting message #{delete_iterator} in {channel.name}")
                    try:
                        await message.delete()
                    except discord.errors.NotFound:
                        pass
            await channel.send('Reddit server masterlist: <https://www.reddit.com/r/languagelearning/comments/5m5426'
                               '/discord_language_learning_servers_masterlist/>')
            await channel.send('Invite link for public language hub server: https://discord.gg/jxcVmHJ')
            await channel.send('You can copy-paste these two above messages and send them to anyone looking to see a '
                               'list of all the servers\n\n\n⠀')

        """Post main list"""
        main_iterator = 0

        for part in listFull:  # main
            if len(part) == 18:  # channel IDs
                hub_channel = client.get_channel(int(part))
                continue
            main_iterator += 1
            for channel in [client.germanicServListChan, client.modServListChan]:
                try:
                    print(f'Posting message {main_iterator}/{listFullLen} to {channel.guild}, {channel.name}')
                except AttributeError as e:
                    print(e, channel)
                    continue
                await channel.send(part)

        mobile_iterator = 0
        """Post mobile lists"""
        for line in listMob:
            if len(line) == 18:  # channel IDs
                hub_channel = client.get_channel(int(line))
                continue
            for channel in [hub_channel]:
                mobile_iterator += 1
                print(f'Posting message {mobile_iterator}/{len(listMob) - 6} to {channel.guild}, {channel.name}')
                if line[0:4] == '**__':
                    line = '⠀\n\n\n\n\n``` ```' + line
                else:
                    line = '⠀\n' + line
                if len(line) < 4:
                    continue
                await channel.send(line)

    # for channel in [client.hubServListChan, client.modServListChan]:  # Deletes messages from main lists, and posts
    #     # beginning of lists
    #
    #     print(channel)
    #     try:
    #         await channel.purge(limit=200)
    #     except asyncio.queues.QueueEmpty:
    #         pass
    #     async for message in channel.history():
    #         if is_me(message):
    #             iterator += 1
    #             print('Deleting message {} from {}, {}'.format(iterator, channel.guild, channel.name))
    #             await message.delete()
    #     await channel.send('Reddit server masterlist: <https://www.reddit.com/r/languagelearning/comments/5m5426'
    #                        '/discord_language_learning_servers_masterlist/>')
    #     await channel.send('Invite link for public language hub server: https://discord.gg/jxcVmHJ')
    #     await channel.send('You can copy-paste these two above messages and send them to anyone looking to see a list '
    #                        'of all the servers')
    #     print('Posting list preamble to {}, {}'.format(channel.guild, channel.name))
    # for channel in [client.modServMobileChan, client.hubServMobileChan, client.germanicServListChan]:  # Deletes
    # for channel in [client.hubServMobileChan, client.germanicServListChan]:  # Deletes
    #     # messages from mobile lists
    #     iterator = 0
    #     try:
    #         print(channel.guild.name, channel.name)
    #         await channel.purge(limit=200)
    #     except discord.errors.Forbidden:
    #         pass
    #     async for message in channel.history(limit=None):  # deletes mobile channel messages
    #         if is_me(message):
    #             iterator += 1
    #             print('Deleting message {} from {}, {}'.format(iterator, channel.guild, channel.name))
    #             await message.delete()

    # for part in listFull[i]:
    #     if len(part) < 20:  # channel IDs
    #         print(part)
    #         hub_channel = client.get_channel(int(part))
    #         continue
    #     for channel in [client.modServListChan, hub_channel]:
    #         print('Posting message {}/{} to {},{}'.format(iterator, listFullLen, channel.guild, channel.name))
    #         print(part)
    #         await channel.send(part)

    # iterator = 0
    # listMobLen = len(listMob)
    # for i in range(listMobLen):  # Formats mobile lists, posts the mobile lists
    #     iterator += 1
    #     listMob[i] = listMob[i].replace('app.com/invite', '.gg')
    #     # for channel in [client.germanicServListChan, client.modServMobileChan, client.hubServMobileChan]:
    #     for channel in [client.germanicServListChan, client.hubServMobileChan]:
    #         print('Posting message {}/{} to {},{}'.format(iterator, listMobLen, channel.guild, channel.name))
    #         await channel.send(listMob[i])

    print("Hello everyone, I'm a mod in a couple of the servers of the Discord Language Learning Network, "
          "run inside a web app called Discord (like Skype, but better).  Discord is a great service for "
          "communication with people all over the world, and I think more people should know about it.\n I've "
          "decided to compile a master list of servers for everyone to explore around all the available servers.  "
          "I've put it all in one central hub server (https://discord.gg/jxcVmHJ), but I'll put all the links below "
          "too.  These are all the discord servers for learning languages that I've managed to find anywhere, if "
          "anyone knows of any more, please tell me and I'll add it to my list!\n")  # Makes the Reddit post
    for i in range(len(listMob)):
        if listMob[i][0:4] != '**__' and listMob[i][0:2] == '**':
            listMob[i] = listMob[i].replace('**', '* **', 1)
        if listMob[i][0:4] == '**__':
            listMob[i] = listMob[i].replace('**__', '\n>##', 1).replace('__**', '')
        if not listMob[i]:
            pass
        if listMob[i][0:3] == '539':
            continue
        print(listMob[i])
    print("\n--------------------------\n**If you ever notice anything wrong with any of the servers, anything from "
          "a dead link to abusive administration, please tell me through Reddit or here: https://discord.gg/jxcVmHJ ("
          "additionally, I'm in all the above servers, Ryry013#9234)**")


def getAPIKey(filename):
    f = open(filename)
    return f.read()


key = getAPIKey(dir_path+'/APIKey.txt') + 'k'
client.run(key)
input("press key to exit")
