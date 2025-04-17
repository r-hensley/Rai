import discord
from discord.ext import commands


class Dropdown(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    async def dropdown(self, ctx: commands.Context):
        role_ids = {
            'english': 243853718758359040,
            'spanish': 243854128424550401,
            'other': 247020385730691073,
            'fluentenglish': 708704078540046346,
            'intermediateenglish': 708704480161431602,
            'beginnerenglish': 708704491180130326,
            'fluentspanish': 708704473358532698,
            'intermediatespanish': 708704486994215002,
            'beginnerspanish': 708704495302869003,
            'learningenglish': 247021017740869632,
            'learningspanish': 297415063302832128,
            'heritageenglish': 1001176425296052324,
            'heritagespanish': 1001176351874752512
        }
        
        roles = {name: ctx.guild.get_role(rid) for name, rid in role_ids.items()}
        
        language_roles = {roles['english'], roles['spanish'], roles['other']}
        level_roles = {roles['fluentenglish'], roles['intermediateenglish'], roles['beginnerenglish'],
                       roles['fluentspanish'], roles['intermediatespanish'], roles['beginnerspanish']}
        learning_roles = {roles['learningenglish'], roles['learningspanish']}
        heritage_roles = {roles['heritageenglish'], roles['heritagespanish']}
        all_roles = language_roles | level_roles | learning_roles | heritage_roles
        
        def add_row(role_list, placeholder="Choose an option"):
            # Create a dropdown menu with the above roles
            options = [
                discord.SelectOption(
                    label=role.name,
                    value=str(role.id),
                    default=role in ctx.author.roles,
                ) for
                role in role_list
            ]
            
            select = discord.ui.Select(
                placeholder=placeholder, options=options, max_values=len(role_list))
            
            return select
        
        native_select = add_row(language_roles, "Native Language Roles")
        level_select = add_row(level_roles, "Language Level Roles")
        learning_select = add_row(learning_roles, "Learning Roles")
        heritage_select = add_row(heritage_roles, "Heritage Roles")
        
        async def make_callback(select):
            async def select_callback(interaction: discord.Interaction):
                    selected_roles = select.values
                    await interaction.response.send_message(f"You selected: {', '.join(selected_roles)}")
            return select_callback
            
        native_select.callback = make_callback(native_select)
        level_select.callback = make_callback(level_select)
        learning_select.callback = make_callback(learning_select)
        heritage_select.callback = make_callback(heritage_select)

        # Create a view to hold the dropdown
        view = discord.ui.View()
        view.add_item(native_select)
        view.add_item(level_select)
        view.add_item(learning_select)
        view.add_item(heritage_select)

        await ctx.send("Please select an option from the dropdown:", view=view)
        
async def setup(bot: commands.Bot):
    await bot.add_cog(Dropdown(bot))