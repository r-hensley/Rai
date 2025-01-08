import logging
import urllib
from urllib.request import Request, urlopen

import discord
from bs4 import BeautifulSoup
from discord.ext import commands

from cogs.utils import helper_functions as hf
from cogs.utils.BotUtils import bot_utils as utils

class Dictionary(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @commands.command(aliases=['rae'])
    async def get_rae_results(self, ctx, *, word: str):
        """
        Look up definitions of a word from the Real Academia Española dictionary.
        - Example usage: `j!rae libro`.
        
        This is a command developed by `@jobcuenca`. For inquiries, suggestions, and problem reports,
        you can contact him through the provided Discord account.
        
        -------
        Buscar definiciones de palabras del Diccionario de la Real Academia Española.
        - Ejemplo de uso: `j!rae libro`.
        
        Este comando fue desarrollado por `@jobcuenca`. Para consultas, sugerencias y reportes de problemas,
        puedes contactarlo a través de la cuenta de Discord proporcionada.
        """
        pass  # put code here

async def setup(bot):
    await bot.add_cog(Dictionary(bot))
        