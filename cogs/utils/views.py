import discord


class PaginationView(discord.ui.View):
    """Generic paginated embed view with ◄/►/✖ buttons."""

    def __init__(self, embeds, author, timeout=60):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.author = author
        self.current_page = 0
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.page_indicator.label = f"{self.current_page + 1}/{len(self.embeds)}"
        self.next_button.disabled = self.current_page == len(self.embeds) - 1

    @discord.ui.button(label="◄", style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("You cannot control this menu.", ephemeral=True)
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.gray, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="►", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("You cannot control this menu.", ephemeral=True)
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="✖", style=discord.ButtonStyle.red)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        self.stop()

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.NotFound:
                pass
        self.stop()
