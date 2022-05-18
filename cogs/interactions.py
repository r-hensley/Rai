import asyncio
import os
import re
from typing import Union, List, NamedTuple

import discord
import discord.ext.commands as commands
from typing import Optional
from discord import app_commands, ui

from .utils import helper_functions as hf

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


# @app_commands.describe(): add a description to a parameter when the user is inputting it
# @app_commands.rename():  rename a parameter after it's been defined by the function
# app_commands.context_menu() doesn't work in cogs!


class Point(NamedTuple):
    x: int
    y: int


class Questionnaire(ui.Modal, title='Questionnaire Response'):
    name = ui.TextInput(label='User(s) to report (short field)', style=discord.TextStyle.short)
    answer = ui.TextInput(label='Description of incident (paragraph field)', style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f'Your report has been sent to the mod team!', ephemeral=True)


class PointTransformer(app_commands.Transformer):
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> Point:
        (x, _, y) = value.partition(',')
        return Point(x=int(x.strip()), y=int(y.strip()))


class Interactions(commands.Cog):
    """A module for Discord interactions such as slash commands and context commands"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command()
    async def sync(self, ctx):
        """Syncs app commands"""
        await self.bot.tree.sync(guild=FEDE_GUILD)
        await self.bot.tree.sync(guild=RY_GUILD)
        try:
            await ctx.message.add_reaction("♻")
        except (discord.HTTPException, discord.Forbidden):
            pass

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

        view = ui.View()
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
            interaction: discord.Interaction,
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

        alarm_emb = discord.Embed(title=f"Staff Ping",
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
            alarm_emb.add_field(name="Reported message content", value=ref_msg.content)

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

        class MyView(ui.View):
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
                mod_channel_id = None
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
                mod_channel_id = None
                # guild had a mod channel once but it seems it has been deleted

        if not mod_channel:
            return  # this guild does not have any kind of mod channel configured

        # Send notification to a mod channel
        content = None
        staff_role_id = ""
        if slash:
            config = self.bot.db['staff_ping'].get(guild_id)
            if config:
                staff_role_id = config.get("role")  # try to get role id from staff_ping db
                if not staff_role_id:  # no entry in staff_ping db
                    staff_role_id = self.bot.db['mod_role'].get(guild_id, {}).get("id")
        if staff_role_id:
            content = f"<@&{staff_role_id}>"
        msg = await hf.safe_send(mod_channel, content, embed=alarm_emb, view=view)

        # Send notification to users who subscribe to mod pings
        for user_id in self.bot.db['staff_ping'].get(guild_id, {}).get('users', []):
            try:
                user = self.bot.get_user(user_id)
                if user:
                    notif = await hf.safe_send(user, embed=alarm_emb)
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
        view = ui.View()
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

            await interaction.delete_original_message()
            await self.edit_embed(button_interaction, working_embed_msg)

        async def edit_embed_button_callback(button_interaction: discord.Interaction):
            """
            Launch edit_embed()
            """
            await self.edit_embed(button_interaction, msg=None)

        async def exit_menu_button_callback(button_interaction: discord.Interaction):
            """
            Delete config menu
            """
            try:
                await interaction.delete_original_message()
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
        view = ui.View()
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
                    guild_id = submit_self.answer.value.split('/')[-3]
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
                    await interaction.delete_original_message()
                    await self.edit_embed(interaction, msg=None)

        view = ui.View()
        view.add_item(input_jump_url_button)

        async def button_callback(button_interaction: discord.Interaction):
            modal = JumpURLModal()
            await button_interaction.response.send_modal(modal)  # This should make a call to edit_embed()

        input_jump_url_button.callback = button_callback

        await interaction.response.send_message(embed=msg_find_embed, view=view)




async def setup(bot):
    await bot.add_cog(Interactions(bot))
