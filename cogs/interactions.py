import asyncio
import os
import re
from typing import Union, List, NamedTuple
import aiohttp
from io import BytesIO

import asqlite
import discord
import discord.ext.commands as commands
from typing import Optional
from discord import app_commands, ui

from .utils import helper_functions as hf
from cogs.utils.BotUtils import bot_utils as utils

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
BANS_CHANNEL_ID = 329576845949534208
MODCHAT_SERVER_ID = 257984339025985546
RYRY_SPAM_CHAN = 275879535977955330
JP_SERVER_ID = 189571157446492161
SP_SERVER_ID = 243838819743432704
CH_SERVER_ID = 266695661670367232
CL_SERVER_ID = 320439136236601344
RY_SERVER_ID = 275146036178059265
FEDE_TESTER_SERVER_ID = 941155953682821201

RY_GUILD = discord.Object(id=RY_SERVER_ID)
FEDE_GUILD = discord.Object(id=FEDE_TESTER_SERVER_ID)
SP_GUILD = discord.Object(id=SP_SERVER_ID)
JP_GUILD = discord.Object(id=JP_SERVER_ID)

DATABASE_PATH = rf'{dir_path}/database.db'


# @app_commands.describe(): add a description to a parameter when the user is inputting it
# @app_commands.rename():  rename a parameter after it's been defined by the function
# app_commands.context_menu() doesn't work in cogs!


async def on_tree_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    qualified_name = getattr(interaction.command, 'qualified_name', None)
    e = discord.Embed(title=f'App Command Error ({interaction.type})', colour=0xcc3366)
    if qualified_name:
        e.add_field(name='Name', value=qualified_name)
    e.add_field(name='Author', value=interaction.user)

    fmt = f'Channel: {interaction.channel} (ID: {interaction.channel.id})'
    if interaction.guild:
        fmt = f'{fmt}\nGuild: {interaction.guild} (ID: {interaction.guild.id})'

    e.add_field(name='Location', value=fmt, inline=False)

    if interaction.data:
        e.add_field(name="Data", value=f"```{interaction.data}```")

    if interaction.extras:
        e.add_field(name="Extras", value=f"```{interaction.extras}```")

    await utils.send_error_embed(interaction.client, interaction, error, e)


class Point(NamedTuple):
    x: int
    y: int


class Questionnaire(ui.Modal, title='Questionnaire Response'):
    name = ui.TextInput(label='User(s) to report (short field)', style=discord.TextStyle.short)
    answer = ui.TextInput(label='Description of incident (paragraph field)', style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message('Your report has been sent to the mod team!', ephemeral=True)


class ModlogReasonModal(ui.Modal, title='Modlog Entry Reason'):
    default_reason = "Muted with command shortcut"
    reason = ui.TextInput(label='(Optional) Input a reason for the mute',
                          style=discord.TextStyle.paragraph,
                          required=False,
                          default=default_reason,
                          placeholder=default_reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("I will attempt to mute the user with the reason you gave.",
                                                ephemeral=True)


class BanModal(ui.Modal, title='Ban Menu'):
    default_reason = "Banned with command shortcut"
    reason = ui.TextInput(label='(Optional) Input a reason for the ban',
                          style=discord.TextStyle.paragraph,
                          required=True,
                          default=default_reason,
                          placeholder=default_reason,
                          max_length=512 - len("*by* <@202995638860906496> \n**Reason:** ") - 32)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("I've edited the ban reason (check to make sure the reason "
                                                "above properly changed).",
                                                ephemeral=True)


class LogReason(ui.Modal, title='Input Log Reason'):
    default_reason = "(no additional reason given)"
    reason = ui.TextInput(label='Input a reason or context for the log',
                          style=discord.TextStyle.paragraph,
                          required=True,
                          default=default_reason,
                          placeholder=default_reason,
                          max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("I'll attempt to log the message now.", ephemeral=True)


class PointTransformer(app_commands.Transformer):
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> Point:
        (x, _, y) = value.partition(',')
        return Point(x=int(x.strip()), y=int(y.strip()))


class Interactions(commands.Cog):
    """A module for Discord interactions such as slash commands and context commands"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot.tree.on_error = on_tree_error

    async def sync_main(self):
        """Main code for syncing app commands"""
        # Sync interactions here in this file
        bot_guilds = [g.id for g in self.bot.guilds]
        # for guild_id in [FEDE_TESTER_SERVER_ID]:
        # temporarily disable slash commands in fede's test server from disuse
        self.bot.tree.copy_global_to(guild=RY_GUILD)
        for guild_id in []:  # these are synced in hf.hf_sync() command
            if guild_id in bot_guilds:
                guild_object = discord.Object(id=guild_id)
                await self.bot.tree.sync(guild=guild_object)

        await self.bot.tree.sync()  # global commands

        # Sync context commands in helper_functions()
        await hf.hf_sync()

    @commands.command()
    async def sync(self, ctx: Optional[commands.Context]):
        """Syncs app commands"""
        await self.sync_main()

        try:
            await ctx.message.add_reaction("♻")
        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            await utils.safe_send(ctx, "**`interactions: commands synced`**", delete_after=5.0)

    @app_commands.command()
    @app_commands.guilds(FEDE_GUILD)
    async def modal(self, interaction: discord.Interaction):
        """Sends a modal (hopefully)"""
        await interaction.response.send_modal(Questionnaire())

    @app_commands.command()
    @app_commands.guilds(FEDE_GUILD)
    async def buttons(self, interaction: discord.Interaction):
        """Adds buttons to a message"""
        button_1 = ui.Button(style=discord.ButtonStyle.primary,
                             label="Primary button",
                             row=0)
        button_2 = ui.Button(style=discord.ButtonStyle.secondary,
                             label="Secondary button",
                             row=0)
        dropdown = ui.Select(placeholder="Default placeholder text",  # shows if no options are selected
                             options=[
                                 discord.SelectOption(label="Choice 1",
                                                      value="Choice 1 value",
                                                      description="Choice 1 description",
                                                      emoji="🍏",
                                                      default=False),
                                 discord.SelectOption(label="Choice 2",
                                                      value="Choice 2 value",
                                                      description="Choice 2 description",
                                                      emoji="🍎")
                             ],
                             row=1,
                             min_values=1,
                             max_values=2)

        view = utils.RaiView()
        view.add_item(button_1)
        view.add_item(button_2)
        view.add_item(dropdown)

        await interaction.response.send_message("UI elements will be attached to this", view=view)

    @app_commands.command()
    @app_commands.guilds(FEDE_GUILD)
    async def fruits_app_command(self, interaction: discord.Interaction, fruits: str):
        await interaction.response.send_message(f'Your favourite fruit seems to be {fruits}')

    @fruits_app_command.autocomplete('fruits')
    async def fruits_autocomplete(
            self,
            _,
            current: str,
    ) -> List[app_commands.Choice[str]]:
        fruits = ['Banana', 'Pineapple', 'Apple', 'Watermelon', 'Melon', 'Cherry']
        return [
            app_commands.Choice(name=fruit, value=fruit)
            for fruit in fruits if current.lower() in fruit.lower()
        ]

    @app_commands.command()
    @app_commands.guilds(FEDE_TESTER_SERVER_ID, RY_SERVER_ID)
    @app_commands.describe(member='the member to ban')
    async def ban_describe(self, interaction: discord.Interaction, member: discord.Member):
        """Describes the given parameters by their name using the key of the keyword argument as the name."""
        await interaction.response.send_message(f'Banned {member}')

    @app_commands.command()
    @app_commands.guilds(FEDE_TESTER_SERVER_ID, RY_SERVER_ID)
    @app_commands.rename(the_member_to_ban='memberrrr')
    async def ban_rename(self, interaction: discord.Interaction, the_member_to_ban: discord.Member):
        """Renames the given parameters by their name using the key of the keyword argument as the name."""
        await interaction.response.send_message(f'Banned {the_member_to_ban}')

    @app_commands.command()
    @app_commands.guilds(FEDE_TESTER_SERVER_ID, RY_SERVER_ID)
    @app_commands.describe(fruits='fruits to choose from')
    @app_commands.choices(fruits=[
        app_commands.Choice(name='apple', value=1),
        app_commands.Choice(name='banana', value=2),
        app_commands.Choice(name='cherry', value=3),
    ])
    async def fruit_choice(self, interaction: discord.Interaction, fruits: app_commands.Choice[int]):
        """Instructs the given parameters by their name to use the given choices for their choices."""
        await interaction.response.send_message(f'Your favourite fruit is {fruits.name}.')

    @app_commands.command()
    @app_commands.guilds(FEDE_TESTER_SERVER_ID, RY_SERVER_ID)
    async def graph(
            self,
            interaction: discord.Interaction,
            point: app_commands.Transform[Point, PointTransformer],
    ):
        """The base class that allows a type annotation in an application command parameter to map
        into a AppCommandOptionType and transform the raw value into one from this type.

        This class is customisable through the overriding of classmethod() in the class and by using
        it as the second type parameter of the Transform class. For example, to convert
        a string into a custom pair type:

        A type annotation that can be applied to a parameter to customise the behaviour of an option type
        by transforming with the given Transformer. This requires the usage of two generic parameters,
        the first one is the type you’re converting to and the second one is the type of the
        Transformer actually doing the transformation.

        During type checking time this is equivalent to typing.Annotated so type checkers
        understand the intent of the code."""
        await interaction.response.send_message(str(point))

    @app_commands.command()
    @app_commands.guilds(FEDE_TESTER_SERVER_ID, RY_SERVER_ID)
    async def range(self, interaction: discord.Interaction, value: app_commands.Range[int, 10, 12]):
        await interaction.response.send_message(f'Your value is {value}', ephemeral=True)

    @app_commands.command()
    @app_commands.guilds(SP_GUILD)
    async def emojiname(self, interaction: discord.Interaction, emoji: str):
        """Puts an emoji in your name"""
        user = interaction.user
        if re.search(r"<:.*:\d{17,22}>", emoji):
            await interaction.response.send_message("I think you're trying to add a custom emoji to your name, but "
                                                    "I can't add custom emojis to names! Please try again",
                                                    ephemeral=True)
            return

        try:
            await user.edit(nick=user.display_name + emoji)
        except discord.Forbidden:
            await interaction.response.send_message("I lack the ability to edit your nickname!", ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message("I couldn't add your text to your nickname! Maybe the resulting "
                                                    "nickname was too long?", ephemeral=True)
        else:
            await interaction.response.send_message("I've added that to your nickname!", ephemeral=True)

    #
    #
    # ########################################
    #
    # Staff ping slash command module
    #
    # ########################################
    #
    #

    @app_commands.command()
    @app_commands.guilds(FEDE_TESTER_SERVER_ID, RY_SERVER_ID)
    async def staffping(self, interaction: discord.Interaction, users: str, reason: str):
        """Notifies the staff team about a current and urgent issue."""
        await self.staffping_code(interaction, users, reason)

    async def staffping_code(self,
                             ctx: Union[discord.Interaction, commands.Context],
                             users: str,
                             reason: str):
        """The main code for the staffping command. This will be referenced by the above slash
        command, but also by the mods_ping() function in on_message()"""
        regex_result: List[str] = re.findall(r'<?@?!?(\d{17,22})>?', users)

        slash = isinstance(ctx, discord.Interaction)

        channel = ctx.channel
        last_message: discord.Message = ctx.channel.last_message
        if not last_message:
            last_message = [message async for message in channel.history(limit=1)][0]
        jump_url = getattr(last_message, "jump_url", None)

        # If it's a message with a staff ping, try to find if the user responded to a message in the report
        ref_msg = None
        if not slash:
            if reference := ctx.message.reference:
                if ref_msg := reference.cached_message:
                    regex_result.append(str(ref_msg.author.id))

        if not regex_result:
            if slash:
                await ctx.response.send_message("I couldn't find the specified user(s).\n"
                                                "Please, mention the user/s or write their ID/s in the user prompt.",
                                                ephemeral=True)
                return
            else:
                pass

        for result in regex_result:
            if not ctx.guild.get_member(int(result)):
                regex_result.remove(result)
                if slash:
                    await ctx.response.send_message(f"I couldn't find the user {result} in this server", ephemeral=True)

        if not regex_result and slash:
            await ctx.response.send_message("I couldn't find any of the users that you specified, try again.\n"
                                            "Please, mention the user/s or write their ID/s in the user prompt.",
                                            ephemeral=True)
            return

        member_list: List[str] = list(set(regex_result))  # unique list of users

        if len(member_list) > 9:
            if slash:
                await ctx.response.send_message(
                    "You're trying to report too many people at the same time. Max per command: 9.\n"
                    "Please, mention the user/s or write their ID/s in the user prompt.",
                    ephemeral=True)
                return
            else:
                member_list = []

        invis = "⠀"  # an invisible character that's not a space to avoid stripping of whitespace
        user_id_list = [f'\n{invis * 1}- <@{i}> (`{i}`)' for i in member_list]
        user_id_str = ''.join(user_id_list)
        if slash:
            confirmation_text = f"You've reported the user: {user_id_str} \nReason: {reason}."
            if len(member_list) > 1:
                confirmation_text = confirmation_text.replace('user', 'users')
            await ctx.response.send_message(f"{confirmation_text}", ephemeral=True)

        if slash:
            from_text = f"{ctx.user.mention} ({ctx.user.name})"
        else:
            from_text = f"{ctx.author.mention} ({ctx.author.name})"

        alarm_emb = discord.Embed(title="Staff Ping",
                                  description=f"- **From**: {from_text}"
                                              f"\n- **In**: {ctx.channel.mention}",
                                  color=discord.Color(int('FFAA00', 16)),
                                  timestamp=discord.utils.utcnow())
        if jump_url:
            alarm_emb.description += f"\n[**`JUMP URL`**]({jump_url})"
        if reason:
            alarm_emb.description += f"\n\n- **Reason**: {reason}."
        if user_id_str:
            alarm_emb.description += f"\n- **Reported Users**: {user_id_str}"
        if ref_msg:
            alarm_emb.add_field(name="Reported message content", value=ref_msg.content[:1024])

        button_author = discord.ui.Button(label='0', style=discord.ButtonStyle.primary)

        button_1 = discord.ui.Button(label='1', style=discord.ButtonStyle.gray)
        button_2 = discord.ui.Button(label='2', style=discord.ButtonStyle.gray)
        button_3 = discord.ui.Button(label='3', style=discord.ButtonStyle.gray)
        button_4 = discord.ui.Button(label='4', style=discord.ButtonStyle.gray)
        button_5 = discord.ui.Button(label='5', style=discord.ButtonStyle.gray)
        button_6 = discord.ui.Button(label='6', style=discord.ButtonStyle.gray)
        button_7 = discord.ui.Button(label='7', style=discord.ButtonStyle.gray)
        button_8 = discord.ui.Button(label='8', style=discord.ButtonStyle.gray)
        button_9 = discord.ui.Button(label='9', style=discord.ButtonStyle.gray)

        button_solved = discord.ui.Button(label='Mark as Solved', style=discord.ButtonStyle.green)

        buttons = [button_author, button_1, button_2, button_3, button_4,
                   button_5, button_6, button_7, button_8, button_9]

        class MyView(utils.RaiView):
            def __init__(self, timeout):
                super().__init__(timeout=timeout)

            async def on_timeout(self):
                await msg.edit(view=None)

        view = MyView(timeout=86400)
        for button in buttons[:len(member_list) + 1]:
            view.add_item(button)
        view.add_item(button_solved)

        if slash:
            interaction_ctx = await self.bot.get_context(ctx)

        async def button_callback_action(button_index):
            if button_index == 0:
                if slash:
                    modlog_target = ctx.user.id
                else:
                    modlog_target = ctx.author.id
            else:
                modlog_target = member_list[int(button_index) - 1]

            modlog_command: commands.Command = self.bot.get_command("modlog")
            if slash:
                embed = await interaction_ctx.invoke(modlog_command,
                                                     id_in=modlog_target,
                                                     delete_parameter=30,
                                                     post_embed=False)
            else:
                embed = await ctx.invoke(modlog_command,
                                         id_in=modlog_target,
                                         delete_parameter=30,
                                         post_embed=False)
            return embed, modlog_target

        async def author_button_callback(button_interaction: discord.Interaction):
            embed, modlog_target = await button_callback_action(0)
            await button_interaction.response.send_message(modlog_target, embed=embed, ephemeral=True)

        button_author.callback = author_button_callback

        async def button_1_callback(button_interaction: discord.Interaction):
            embed, modlog_target = await button_callback_action(1)
            await button_interaction.response.send_message(modlog_target, embed=embed, ephemeral=True)

        button_1.callback = button_1_callback

        async def button_2_callback(button_interaction: discord.Interaction):
            embed, modlog_target = await button_callback_action(2)
            await button_interaction.response.send_message(modlog_target, embed=embed, ephemeral=True)

        button_2.callback = button_2_callback

        async def button_3_callback(button_interaction: discord.Interaction):
            embed, modlog_target = await button_callback_action(3)
            await button_interaction.response.send_message(modlog_target, embed=embed, ephemeral=True)

        button_3.callback = button_3_callback

        async def button_4_callback(button_interaction: discord.Interaction):
            embed, modlog_target = await button_callback_action(4)
            await button_interaction.response.send_message(modlog_target, embed=embed, ephemeral=True)

        button_4.callback = button_4_callback

        async def button_5_callback(button_interaction: discord.Interaction):
            embed, modlog_target = await button_callback_action(5)
            await button_interaction.response.send_message(modlog_target, embed=embed, ephemeral=True)

        button_5.callback = button_5_callback

        async def button_6_callback(button_interaction: discord.Interaction):
            embed, modlog_target = await button_callback_action(6)
            await button_interaction.response.send_message(modlog_target, embed=embed, ephemeral=True)

        button_6.callback = button_6_callback

        async def button_7_callback(button_interaction: discord.Interaction):
            embed, modlog_target = await button_callback_action(7)
            await button_interaction.response.send_message(modlog_target, embed=embed, ephemeral=True)

        button_7.callback = button_7_callback

        async def button_8_callback(button_interaction: discord.Interaction):
            embed, modlog_target = await button_callback_action(8)
            await button_interaction.response.send_message(modlog_target, embed=embed, ephemeral=True)

        button_8.callback = button_8_callback

        async def button_9_callback(button_interaction: discord.Interaction):
            embed, modlog_target = await button_callback_action(9)
            await button_interaction.response.send_message(modlog_target, embed=embed, ephemeral=True)

        button_9.callback = button_9_callback

        async def solved_button_callback(button_interaction: discord.Interaction):
            new_embed = msg.embeds[0]
            new_embed.color = 0x77B255  # green background color of the checkmark ✅
            new_embed.title = "~~Staff Ping~~ RESOLVED ✅"
            new_embed.set_footer(text=f"Resolved by {str(button_interaction.user)}")
            await msg.edit(view=None, embed=new_embed)
            await msg.add_reaction("✅")

        button_solved.callback = solved_button_callback

        guild_id = str(ctx.guild.id)

        # Try to find the channel set by the staffping command first
        mod_channel = None
        mod_channel_id = self.bot.db['staff_ping'].get(guild_id, {}).get("channel")
        if mod_channel_id:
            mod_channel = ctx.guild.get_channel_or_thread(mod_channel_id)
            if not mod_channel:
                del self.bot.db['staff_ping'][guild_id]['channel']
                # guild had a staff ping channel once but it seems it has been deleted

        # Failed to find a staffping channel, search for a submod channel next
        mod_channel_id = self.bot.db['submod_channel'].get(guild_id)
        if not mod_channel and mod_channel_id:
            mod_channel = ctx.guild.get_channel_or_thread(mod_channel_id)
            if not mod_channel:
                del self.bot.db['submod_channel'][guild_id]
                mod_channel_id = None
                # guild had a submod channel once but it seems it has been deleted

        # Failed to find a submod channel, search for mod channel
        if not mod_channel and mod_channel_id:
            mod_channel_id = self.bot.db['mod_channel'].get(guild_id)
            mod_channel = ctx.guild.get_channel_or_thread(mod_channel_id)
            if not mod_channel:
                del self.bot.db['mod_channel'][guild_id]
                # guild had a mod channel once but it seems it has been deleted

        if not mod_channel:
            return  # this guild does not have any kind of mod channel configured

        # Send notification to a mod channel
        # if it came from a slash command, insert a ping to staff here
        content = None
        staff_role_id = ""
        if slash:
            config = self.bot.db['staff_ping'].get(guild_id)
            if config:
                staff_role_id = config.get("role")  # try to get role id from staff_ping db
                if not staff_role_id:  # no entry in staff_ping db
                    staff_role_id = self.bot.db['mod_role'].get(guild_id, {}).get("id")
                    if isinstance(staff_role_id, list):
                        staff_role_id = staff_role_id[0]
        if staff_role_id:
            content = f"<@&{staff_role_id}>"
        msg = await utils.safe_send(mod_channel, content, embed=alarm_emb, view=view)

        # Send notification to users who subscribe to mod pings
        for user_id in self.bot.db['staff_ping'].get(guild_id, {}).get('users', []):
            try:
                user = self.bot.get_user(user_id)
                if user:
                    notif = await utils.safe_send(user, embed=alarm_emb)
                    if hasattr(self.bot, 'synced_reactions'):
                        self.bot.synced_reactions.append((notif, msg))

                    else:
                        self.bot.synced_reactions = [(notif, msg)]
            except discord.Forbidden:
                pass

        return msg

    #
    #
    # #########################################
    #
    # Dynamic embeds editing module
    #
    # #########################################
    #
    #

    @app_commands.command()
    @app_commands.guilds(FEDE_TESTER_SERVER_ID, RY_SERVER_ID)
    async def embeds(self, interaction: discord.Interaction):
        """A configuration menu for setting up dynamic reaction embeds"""
        await self.main_embed_setup_menu(interaction)

    async def main_embed_setup_menu(self, interaction: discord.Interaction):
        # Define the embed and three buttons
        embed = discord.Embed(description="Use the buttons in this embed to setup or edit dynamic embeds"
                                          "in this server")

        create_embed_button = ui.Button(style=discord.ButtonStyle.primary,
                                        label="Create new embed",
                                        row=0)
        edit_embed_button = ui.Button(style=discord.ButtonStyle.secondary,
                                      label="Edit existing embed",
                                      row=0)
        exit_menu_button = ui.Button(style=discord.ButtonStyle.red,
                                     label="Exit this menu",
                                     row=1)

        # Set up the view with the three buttons
        view = utils.RaiView()
        view.add_item(create_embed_button)
        view.add_item(edit_embed_button)
        view.add_item(exit_menu_button)

        # Send the initial setup menu
        try:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
        except discord.Forbidden:
            return

        async def create_embed_button_callback(button_interaction: discord.Interaction):
            """
            Create embed callback should send a blank template embed and then launch the edit_embed code on it
            """
            template_embed = discord.Embed(title="Title", description="Description")
            template_embed.set_footer(text="Footer")

            try:
                # Template embed to edit
                working_embed_msg = await interaction.channel.send(embed=template_embed)
            except discord.Forbidden:
                return

            await interaction.delete_original_response()
            await self.edit_embed(button_interaction, working_embed_msg)

        async def edit_embed_button_callback(button_interaction: discord.Interaction):
            """
            Launch edit_embed()
            """
            await self.edit_embed(button_interaction, msg=None)

        async def exit_menu_button_callback(_):
            """
            Delete config menu
            """
            try:
                await interaction.delete_original_response()
            except (discord.Forbidden, discord.HTTPException):
                pass

        # Add callbacks to the buttons
        create_embed_button.callback = create_embed_button_callback
        edit_embed_button.callback = edit_embed_button_callback
        exit_menu_button.callback = exit_menu_button_callback

    async def edit_embed(self, interaction: discord.Interaction, msg: Optional[discord.Message]):
        """
        A module for editing an embed
        """
        if not msg:
            # Try to find a message then once it's found, call edit_embed again
            msg = await self.get_embed_msg_to_edit(interaction)
            await self.edit_embed(interaction=interaction, msg=msg)
            return

        embed = discord.Embed(description="Click the following buttons to edit the above embed")

        add_button_button = ui.Button(style=discord.ButtonStyle.primary,
                                      label="Add a button",
                                      row=0)
        add_dropdown_menu_button = ui.Button(style=discord.ButtonStyle.primary,
                                             label="Add a dropdown menu",
                                             row=0)
        remove_element_button = ui.Button(style=discord.ButtonStyle.primary,
                                          label="Remove a button/menu",
                                          row=1)
        edit_embed_text_button = ui.Button(style=discord.ButtonStyle.primary,
                                           label="Edit embed text",
                                           row=2)

        # Setup the view with the three buttons
        view = utils.RaiView()
        view.add_item(add_button_button)
        view.add_item(add_dropdown_menu_button)
        view.add_item(remove_element_button)
        view.add_item(edit_embed_text_button)

        # Send the embed edit menu
        try:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
        except discord.Forbidden:
            return

    async def get_embed_msg_to_edit(self, interaction: discord.Interaction):
        msg_find_embed = discord.Embed(description="Please copy a Jump URL to the message with the embed you "
                                                   "want to edit. Once you have that, click the below button.")
        input_jump_url_button = ui.Button(style=discord.ButtonStyle.primary,
                                          label="Input Jump URL",
                                          row=0)

        class JumpURLModal(ui.Modal, title='Input Jump URL'):
            name = ui.Select(placeholder="Default placeholder text",  # shows if no options are selected
                             options=[
                                 discord.SelectOption(label="Choice 1",
                                                      value="Choice 1 value",
                                                      description="Choice 1 description",
                                                      emoji="🍏",
                                                      default=False),
                                 discord.SelectOption(label="Choice 2",
                                                      value="Choice 2 value",
                                                      description="Choice 2 description",
                                                      emoji="🍎")
                             ],
                             row=1,
                             min_values=1,
                             max_values=2)
            answer = ui.TextInput(label='Please paste the Jump URL here',
                                  style=discord.TextStyle.paragraph,
                                  required=True,
                                  placeholder="https://discord.com/channels/123/456/789")

            async def on_submit(submit_self, modal_interaction: discord.Interaction):
                try:
                    channel_id = submit_self.answer.value.split('/')[-2]
                    message_id = submit_self.answer.value.split('/')[-1]
                    channel = self.bot.get_channel(int(channel_id))
                    msg = await channel.fetch_message(int(message_id))
                    if not msg:
                        raise ValueError
                    await self.edit_embed(interaction, msg=msg)
                except (IndexError, ValueError):
                    await modal_interaction.response.send_message("Please input a Jump URL like "
                                                                  "https://discord.com/channels/123/456/789.")
                    await interaction.delete_original_response()
                    await self.edit_embed(interaction, msg=None)

        view = utils.RaiView()
        view.add_item(input_jump_url_button)

        async def button_callback(button_interaction: discord.Interaction):
            modal = JumpURLModal()
            await button_interaction.response.send_modal(modal)  # This should make a call to edit_embed()

        input_jump_url_button.callback = button_callback

        await interaction.response.send_message(embed=msg_find_embed, view=view)

    #
    #
    # #########################################
    #
    # Dynamic embeds editing module
    #
    # #########################################
    #
    #

    categorylock = app_commands.Group(name="categorylock", description="Settings for voice locking of new users",
                                      guild_ids=[SP_SERVER_ID])

    categorylock_set = app_commands.Group(name="set", parent=categorylock, description="Set a value for new users",
                                          guild_ids=[SP_SERVER_ID])

    @categorylock.command()
    @app_commands.default_permissions()
    @app_commands.describe(category="Choose the category you wish to lock or unlock")
    async def togglecategory(self, interaction: discord.Interaction, category: discord.CategoryChannel = None):
        """Voice lock a category for new users. Send no args to view current locked categories."""
        # See sp_serv_new_user_voice_lock() in events.py

        if not hf.admin_check(interaction):
            await interaction.response.send_message("You cannot use this command.", ephemeral=True)

        s = ''
        if category:
            config = self.bot.db['voice_lock'].setdefault(str(interaction.guild.id), {'categories': {}})
            previous_state = config['categories'].setdefault(str(category.id), False)
            if previous_state is None:
                await interaction.response.send_message("There has been an error, the database read `None`",
                                                        ephemeral=True)
                return
            else:
                if not previous_state:  # new state is True
                    new_state = "enabled"
                else:
                    new_state = "disabled"
                guild_id = str(interaction.guild.id)
                self.bot.db['voice_lock'][guild_id]['categories'][str(category.id)] = not previous_state
                s += f"Voice locking for new users in {category.name} is now {new_state}.\n\n"

        s += "The list of current categories with voice locking enabled is:\n"
        for category in self.bot.db['voice_lock'][str(interaction.guild.id)]['categories']:
            category = discord.utils.get(interaction.guild.channels, id=int(category))
            if self.bot.db['voice_lock'][str(interaction.guild.id)]['categories'][str(category.id)]:
                s += f"- {category.name.upper()}\n"

        await interaction.response.send_message(s, ephemeral=True)

    @categorylock_set.command()
    @app_commands.default_permissions()
    @app_commands.choices(new_user=[discord.app_commands.Choice(name="Newly created accounts", value=1),
                                    discord.app_commands.Choice(name="All new users", value=2)])
    @app_commands.describe(new_user="Do you want to set the limit for newly created accounts or all new users?")
    @app_commands.describe(number_of_hours="How many hours should members have to wait before they can join voice?")
    async def hourlimit(self, interaction: discord.Interaction, new_user: discord.app_commands.Choice[int],
                        number_of_hours: int):
        """Set the number of hours new members to the server should have to wait before joining voice?"""
        config = self.bot.db['voice_lock'].get(str(interaction.guild.id))
        if new_user.value == 1:
            config['hours_for_new_users'] = number_of_hours
            await interaction.response.send_message(f"Newly made accounts now will have to be at least "
                                                    f"{number_of_hours} hours old before they can join voice.",
                                                    ephemeral=True)
        else:
            config['hours_for_users'] = number_of_hours
            await interaction.response.send_message(f"New users will have to wait {number_of_hours} hours before "
                                                    f"joining voice", ephemeral=True)

    @categorylock_set.command()
    @app_commands.describe(number_of_messages="How many messages should members have before they can join voice?")
    async def messagelimit(self, interaction: discord.Interaction, number_of_messages: int):
        """Set num. of messages required for new users to join voice (if not meeting time requirement)"""
        config = self.bot.db['voice_lock'].get(str(interaction.guild.id))
        config['messages_for_users'] = number_of_messages
        await interaction.response.send_message("New users under the required number of hours in the server "
                                                f"will require {number_of_messages} messages before they can "
                                                f"join voice.", ephemeral=True)

    @app_commands.command()
    @app_commands.guilds(SP_SERVER_ID)
    @app_commands.default_permissions(manage_roles=True)
    async def approveforvoice(self, interaction: discord.Interaction, member: discord.Member):
        """Approve a new user for entering the voice chats before they've waited the typical two hours."""
        voice_approved_role = interaction.guild.get_role(978148690873167973)
        try:
            if voice_approved_role not in member.roles:
                await member.add_roles(voice_approved_role)
                await interaction.response.send_message(f"I've successfully attached the role to {member.mention}.",
                                                        ephemeral=False)

            else:
                emb = utils.green_embed("This user already has the Voice Approved role. Do you wish to remove it?")
                remove_button = ui.Button(label="Yes, remove it")
                keep_button = ui.Button(label="No, keep it")
                view = utils.RaiView()

                async def remove_callback(button_interaction: discord.Interaction):
                    await member.remove_roles(voice_approved_role)
                    await button_interaction.response.send_message(
                        f"I've successfully removed the role from {member.mention}.",
                        ephemeral=True)
                    await interaction.edit_original_response(content="⁣", embed=None, view=None)

                async def keep_callback(button_interaction: discord.Interaction):
                    await button_interaction.response.send_message(
                        f"I'll keep the role on {member.mention}.",
                        ephemeral=True)
                    await interaction.edit_original_response(content="⁣", embed=None, view=None)

                view.add_item(remove_button)
                view.add_item(keep_button)
                remove_button.callback = remove_callback
                keep_button.callback = keep_callback

                await interaction.response.send_message(embed=emb, view=view, ephemeral=False)

                async def on_timeout():
                    await interaction.edit_original_response(view=None)

                view.on_timeout = on_timeout

        except discord.Forbidden:
            await interaction.response.send_message("I failed to attach the role to the user. It seems I can't edit "
                                                    "their roles.", ephemeral=True)

    @staticmethod
    async def delete_and_log(interaction: discord.Interaction, message: discord.Message):
        ctx = await commands.Context.from_interaction(interaction)
        ctx.author = interaction.user
        delete = ctx.bot.get_command("delete")
        try:
            if await delete.can_run(ctx):
                await ctx.invoke(delete, str(message.id))
                await interaction.response.send_message("The message has been successfully deleted",
                                                        ephemeral=True)
            else:
                await interaction.response.send_message("You don't have the permission to use that command",
                                                        ephemeral=True)
        except commands.BotMissingPermissions:
            await interaction.response.send_message("The bot is missing permissions here to use that command.",
                                                    ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"There was an unknown error in using that command:\n`{e}`",
                                                    ephemeral=True)
            raise

    @staticmethod
    async def context_message_mute(interaction: discord.Interaction, message: discord.Message):
        ctx = await commands.Context.from_interaction(interaction)
        mute = ctx.bot.get_command("mute")
        # ctx.message = ctx.channel.last_message

        try:
            if await mute.can_run(ctx):
                modal = ModlogReasonModal()
                await interaction.response.send_modal(modal)

                def check(i):
                    return i.type == discord.InteractionType.modal_submit and \
                           i.application_id == interaction.application_id

                try:
                    await ctx.bot.wait_for('interaction', timeout=20.0, check=check)
                    reason = modal.reason
                    await ctx.invoke(mute, args=f"{str(message.author.id)} 1h {reason}")
                except asyncio.TimeoutError:
                    return

            else:
                await interaction.response.send_message("You don't have the permission to use that command",
                                                        ephemeral=True)
        except commands.BotMissingPermissions:
            await interaction.response.send_message("The bot is missing permissions here to use that command.",
                                                    ephemeral=True)

    @staticmethod
    async def context_member_mute(interaction: discord.Interaction, member: discord.Member):
        ctx = await commands.Context.from_interaction(interaction)
        ctx.author = interaction.user
        mute = ctx.bot.get_command("mute")

        try:
            if await mute.can_run(ctx):
                modal = ModlogReasonModal()
                await interaction.response.send_modal(modal)

                def modal_return_check(i):
                    return i.type == discord.InteractionType.modal_submit and \
                           i.application_id == interaction.application_id

                try:
                    await ctx.bot.wait_for('interaction', timeout=20.0, check=modal_return_check)
                    reason = modal.reason
                    await ctx.invoke(mute, args=f"{str(member.id)} 1h {reason}")
                except asyncio.TimeoutError:
                    return

            else:
                await interaction.response.send_message("You don't have the permission to use that command",
                                                        ephemeral=True)
        except commands.BotMissingPermissions:
            await interaction.response.send_message("The bot is missing permissions here to use that command.",
                                                    ephemeral=True)

    @staticmethod
    async def ban_and_clear_main(interaction: discord.Interaction,
                                 member_or_message: Union[discord.Message, discord.User]):
        ctx = await commands.Context.from_interaction(interaction)
        ctx.author = interaction.user
        ban = ctx.bot.get_command("ban")
        default_reason = "Banned with command shortcut"
        reason = default_reason

        if isinstance(member_or_message, discord.Message):
            author = member_or_message.author
            ctx.message = member_or_message
        elif isinstance(member_or_message, (discord.User, discord.Member)):
            author = member_or_message
            async for m in ctx.channel.history(limit=10):
                if m:
                    ctx.message = m
                    break
        else:
            raise TypeError(f"Invalid type of member_or_author passed ({type(member_or_message)})")

        emb = utils.red_embed(f"Attempting to ban user {author.mention}. "
                           f"Please select one of the below options.\n\n"
                           f"**- DELETE:** Bans and __deletes the last one day__ of messages.\n"
                           f"**- KEEP:** Bans and preserves messages.\n"
                           f"**- CANCEL:** Cancels the ban")
        emb.add_field(name="Reason", value=reason)

        delete_button = ui.Button(label="DELETE", style=discord.ButtonStyle.red, row=0)
        keep_button = ui.Button(label="KEEP", style=discord.ButtonStyle.red, row=0)
        cancel_button = ui.Button(label="CANCEL", style=discord.ButtonStyle.gray, row=0)
        reason_button = ui.Button(label="Edit ban reason", style=discord.ButtonStyle.primary, row=1)

        view = utils.RaiView()
        view.add_item(delete_button)
        view.add_item(keep_button)
        view.add_item(cancel_button)
        view.add_item(reason_button)

        async def delete_callback(button_interaction: discord.Interaction):
            """Ban user and delete last one day of messages"""
            if button_interaction.user != interaction.user:
                await button_interaction.response.send_message("Those buttons are not for you!", ephemeral=True)
            # Since all user messages will be deleted, we need to make sure the jump url message isn't one of those
            async for message in ctx.channel.history(limit=30):
                if message.author in [author, ctx.guild.me]:
                    continue  # skip all messages by ban target
                ctx.message = message
                break

            await button_interaction.response.send_message("Will ban and delete messages", ephemeral=True)
            try:
                await ctx.invoke(ban, args=f"{str(author.id)} ⁣⁣delete {reason}")
            except commands.MissingPermissions:
                await button_interaction.followup.send("You lack the permission to ban this user.", ephemeral=True)
            await interaction.edit_original_response(content="⁣", embed=None, view=None)

        async def keep_callback(button_interaction: discord.Interaction):
            """Ban user and keep messages"""
            if button_interaction.user != interaction.user:
                await button_interaction.response.send_message("Those buttons are not for you!", ephemeral=True)

            await button_interaction.response.send_message("Will ban and keep messages", ephemeral=True)
            try:
                await ctx.invoke(ban, args=f"{str(author.id)} ⁣⁣keep__ {reason}")
            except commands.MissingPermissions:
                await button_interaction.followup.send("You lack the permission to ban this user.", ephemeral=True)
            await interaction.edit_original_response(content="⁣", embed=None, view=None)

        async def cancel_callback(button_interaction: discord.Interaction):
            """Cancel command, delete embed"""
            if button_interaction.user != interaction.user:
                await button_interaction.response.send_message("Those buttons are not for you!", ephemeral=True)

            await button_interaction.response.send_message(f"Cancelling ban (reason: {reason})", ephemeral=True)
            await interaction.edit_original_response(content="⁣", embed=None, view=None)

        async def reason_callback(button_interaction: discord.Interaction):
            """Edit reason of ban"""
            if button_interaction.user != interaction.user:
                await button_interaction.response.send_message("Those buttons are not for you!", ephemeral=True)

            modal = BanModal()
            await button_interaction.response.send_modal(modal)
            try:
                def modal_return_check(i):
                    """Check to make sure the modal submitted corresponds to the current application"""
                    return i.type == discord.InteractionType.modal_submit and \
                           i.application_id == interaction.application_id

                await ctx.bot.wait_for("interaction", timeout=20.0, check=modal_return_check)
            except asyncio.TimeoutError:
                pass
            else:
                nonlocal reason  # to make the below line assign to the outer scope variable rather than making new one
                reason = modal.reason.value  # edit reason

                # Edit new reason into embed
                emb.set_field_at(0, name=emb.fields[0].name, value=reason)
                await interaction.edit_original_response(embed=emb)

        delete_button.callback = delete_callback
        keep_button.callback = keep_callback
        cancel_button.callback = cancel_callback
        reason_button.callback = reason_callback

        try:
            if await ban.can_run(ctx):
                await interaction.response.send_message(embed=emb, view=view, ephemeral=True)
            else:
                await interaction.response.send_message("You don't have the permission to use that command",
                                                        ephemeral=True)
        except commands.BotMissingPermissions:
            await interaction.response.send_message("Bot is missing the permissions to execute this command",
                                                    ephemeral=True)

    @staticmethod
    async def log_message(interaction: discord.Interaction,
                          message: discord.Message):
        ctx = await commands.Context.from_interaction(interaction)
        # ctx.author = interaction.user
        log = ctx.bot.get_command("log")

        modal = LogReason()

        await interaction.response.send_modal(modal)

        def check(i):
            return i.type == discord.InteractionType.modal_submit and \
                   i.application_id == interaction.application_id

        try:
            await ctx.bot.wait_for("interaction", timeout=60.0, check=check)
            reason = modal.reason
            # Add > to make the whole message quoted
            # Replace [] with () to guarantee the markdown hyperlink works
            content = "> " + message.content
            content = content.replace("\n", "\n> ").replace("[", "(").replace("]", ")")
            text = f"{message.author.id} Logging following message: \n{content[:200]}"
            if len(message.content) > 200:
                text += "..."
            text += f"\n{reason}"

            # add invisible characters to beginning of reason to mark ephemeral for log command
            invisible_space = "⁣⁣"
            text = invisible_space + text

            emb = await ctx.invoke(log, args=text)
            await interaction.followup.send(embed=emb, ephemeral=True)
        except asyncio.TimeoutError:
            return

    change = app_commands.Group(name="change", description="Change a setting in the server",
                                guild_ids=[SP_SERVER_ID])

    @change.command()
    @app_commands.default_permissions()
    @app_commands.describe(message_link="A Jump URL message link to a message")
    @app_commands.describe(message_id="An integer ID for a message")
    @app_commands.describe(url="A URL link to an image on the internet")
    async def banner(self, interaction: discord.Interaction,
                     message_link: str = None,
                     message_id: str = None,
                     url: str = None):
        """Change the server banner to an image of your choice"""
        if not message_link and not message_id and not url:
            await interaction.response.send_message("Please link an image using one of the optional arguments.",
                                                    ephemeral=True)
            return

        if message_link or message_id:
            message: discord.Message = await hf.get_message_from_id_or_link(interaction, message_id, message_link)
            if not message:
                return  # error messages should have been sent from above function

            if message.attachments:
                url = getattr(message.attachments[0], "url", "")
            elif message.embeds:
                url = getattr(message.embeds[0], "url", "")
            else:
                url = ""

            if not url:
                await interaction.response.send_message("I could not find an image in your message. Please try "
                                                        "again with a different message.", ephemeral=True)
                return

        if url:
            try:
                _ = url.split("/")[-1]
            except IndexError:
                await interaction.response.send_message("I had trouble pulling the filename out of the URL. Make sure "
                                                        "the URL ends in something like .../image.png",
                                                        ephemeral=True)
                return
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        cont = BytesIO(await resp.content.read())
                    else:
                        await interaction.response.send_message("I had trouble downloading the image you linked. "
                                                                "Please try again or try a different image."
                                                                f" {message_id}, {message_link}, {url}",
                                                                ephemeral=True)
                        return

            try:
                cont.seek(0)
                old_banner = await interaction.guild.banner.to_file(filename="old_banner.png")
                await interaction.response.send_message("Banner changed. Previous banner is attached below:",
                                                        file=old_banner)
                await interaction.guild.edit(banner=cont.read())
            except discord.Forbidden:
                await interaction.response.send_message("I lacked the permission to edit the banner", ephemeral=True)
                return
            except discord.HTTPException:
                await interaction.response.send_message("I have permission to edit the banner, but something else "
                                                        "went wrong. Maybe the image I tried to use is invalid.",
                                                        ephemeral=True)
                return

    @app_commands.command()
    @app_commands.guilds(RY_GUILD, SP_GUILD, JP_GUILD)
    @app_commands.default_permissions()
    @app_commands.describe(message_link="A Jump URL message link to a message")
    @app_commands.describe(message_id="An integer ID for a message")
    @app_commands.describe(destination_member="The member you want to send the message to")
    @app_commands.describe(destination_id="The ID of the user or channel you want to send the message to")
    async def forward(self,
                      intr: discord.Interaction,
                      message_link: str = None,
                      message_id: str = None,
                      destination_member: discord.Member = None,
                      destination_id: str = None):
        """Forward a message to another user. You must specify either one of message_link/message_id and one of
        destination_member/destination_id."""
        if not destination_member and not destination_id:
            await intr.response.send_message("Please specify either a destination_member or a destination_id",
                                             ephemeral=True)
            return
        if not message_link and not message_id:
            await intr.response.send_message("Please specify either a message_link or a message_id",
                                             ephemeral=True)
            return

        message: discord.Message = await hf.get_message_from_id_or_link(intr, message_id, message_link)
        if not message:
            return

        if not destination_member:
            try:
                destination_id = int(destination_id)
            except ValueError:
                await intr.response.send_message("Please input a valid message ID", ephemeral=True)
                return

            destination_member = intr.guild.get_member(destination_id)
            if not destination_member:
                destination_member = intr.guild.get_channel_or_thread(destination_id)  # a text channel
                if not destination_member:
                    try:
                        destination_member = await self.bot.fetch_user(destination_id)
                    except (discord.NotFound, discord.HTTPException):
                        pass

            if not destination_member:
                await intr.response.send_message("Failed to find the member or channel you specified", ephemeral=True)
                return

        try:
            await utils.safe_send(destination_member, message.content, embeds=message.embeds)
        except (discord.Forbidden, discord.HTTPException) as e:
            await intr.response.send_message(f"Failed to send a message to the user you specified: {e}", ephemeral=True)
            return

        await intr.response.send_message(f"Forwarded {message.jump_url} by {str(message.author)} to "
                                         f"{str(destination_member)}")

    @app_commands.command()
    @app_commands.guilds(SP_SERVER_ID, JP_SERVER_ID, RY_SERVER_ID)
    @app_commands.default_permissions()
    async def invite_all_to_thread(self,
                                   intr: discord.Interaction):
        """Invites all possible members into a thread from the parent text channel without pinging them."""
        list_of_users = []
        if not isinstance(intr.channel, discord.Thread):
            await intr.response.send_message("You can only use this command in a thread", ephemeral=True)
            return

        await intr.response.defer(thinking=True)

        for member in intr.channel.parent.members:
            if member.bot:
                continue
            p = intr.channel.permissions_for(member)
            if p.read_messages:
                list_of_users.append(member)

        if len(list_of_users) > 45:
            await intr.followup.send(f"This command would invite {len(list_of_users)}, but I can only invite a "
                                     f"maximum of 45 users. Sorry!", ephemeral=True)
            return

        ping_message = "Inviting following users:\n" + ", ".join([u.mention for u in list_of_users])
        ping_message += "\n***(Since the mentions in this command were edited in, no users were actually pinged)***"

        try:
            m = await intr.channel.send("Beep")
        except (discord.Forbidden, discord.HTTPException) as e:
            await intr.followup.send("Sorry, I'm unable to message in this channel so I couldn't complete the"
                                     f" command (error: `{e}`)")
            return

        await m.edit(content=ping_message)

        # for member in list_of_users:
        #     try:
        #         await intr.channel.add_user(member)
        #     except (discord.Forbidden, discord.HTTPException):
        #         pass

        await intr.followup.send("I've tried to add everyone I can!")

        await asyncio.sleep(10)
        await m.delete()

    @app_commands.command()
    @app_commands.guilds(RY_SERVER_ID)
    @app_commands.default_permissions()
    @app_commands.describe(user1="The first user to link")
    @app_commands.describe(user2="The second user to link")
    @app_commands.describe(id1="The ID of the first user (if they left the server)")
    @app_commands.describe(id2="The ID of the second user (if they left the server)")
    async def linkusers(self, intr: discord.Interaction,
                        user1: discord.Member = None,
                        user2: discord.Member = None,
                        id1: str = None,
                        id2: str = None):
        """(Choose two arguments only!) Link two user accounts so calling modlog of one brings up the other."""
        if user1:
            id_1 = user1.id
            if id1:
                id1 = None
                await intr.channel.send("Ignoring unneeded `id1` arg (you already have `user1`)", delete_after=10.0)
        elif id1:
            try:
                id_1 = int(id1)
            except ValueError:
                await intr.response.send_message("You must supply an integer for int1")
                return
        else:
            error_msg = "You must choose fill one of either the user option or the ID option for both users!"
            await intr.response.send_message(error_msg, ephemeral=True)
            return

        if user2:
            id_2 = user2.id
            if id2:
                id2 = None
                await intr.channel.send("Ignoring unneeded `id2` arg (you already have `user2`)", delete_after=10.0)
        elif id2:
            try:
                id_2 = int(id2)
            except ValueError:
                await intr.response.send_message("You must supply an integer for int2")
                return
        else:
            error_msg = "You must choose fill one of either the user option or the ID option for both users!"
            await intr.response.send_message(error_msg, ephemeral=True)
            return

        # check to make sure user didn't specify same user in both fields
        if id_1 == id_2:
            error_msg = "You can't link the same user to itself!"
            await intr.response.send_message(error_msg, ephemeral=True)
            return

        await hf.send_to_test_channel(1)

        chosen_args = [i for i in [user1, user2, id1, id2] if i]
        assert len(chosen_args) == 2, "More than two arguments remaining in /linkusers"

        await hf.send_to_test_channel(2, id_1, id_2, intr.guild.id)

        async with asqlite.connect(DATABASE_PATH) as c:
            await c.execute(f"INSERT OR IGNORE INTO users (user_id) VALUES (?)", id_1)
            await c.execute(f"INSERT OR IGNORE INTO users (user_id) VALUES (?)", id_2)
            await c.execute(f"INSERT OR IGNORE INTO guilds (guild_id) VALUES (?)", intr.guild.id)

        await hf.send_to_test_channel(3)

        check_condition = f"((id_1 = ? AND id_2 = ?) OR (id_1 = ? AND id_2 = ?)) AND guild_id = ?"
        check_parameters = (id_1, id_2, id_2, id_1, intr.guild.id)
        async with asqlite.connect(DATABASE_PATH) as c:
            cur = await c.execute(f"SELECT * from linkedusers WHERE {check_condition}", check_parameters)
            res = await cur.fetchall()

        await hf.send_to_test_channel(4, res)

        if res:
            async with asqlite.connect(DATABASE_PATH) as c:
                await c.execute(f"DELETE FROM linkedusers WHERE {check_condition}", check_parameters)
            await intr.response.send_message(f"I've deleted the link between user IDs {id_1} and {id_2}.")
            return

        else:
            async with asqlite.connect(DATABASE_PATH) as c:
                await c.execute(f"INSERT OR IGNORE INTO linkedusers (id_1, id_2, guild_id) VALUES (?, ?, ?)",
                                (id_1, id_2, intr.guild.id))
            await intr.response.send_message(f"I've linked the user's {id_1} and {id_2}.")

        await hf.send_to_test_channel(res, id_1, id_2)


async def setup(bot):
    await bot.add_cog(Interactions(bot))
