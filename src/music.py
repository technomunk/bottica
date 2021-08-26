# Music-playing Cog for the bot

import discord
from discord.ext import commands
from discord_slash import SlashContext, cog_ext
from youtube_dl import YoutubeDL

DATA_FOLDER = 'data/'
CACHE_FOLDER = DATA_FOLDER + 'cache'

YTDL_OPTIONS = {
	'format': 'bestaudio',
	'cachedir': CACHE_FOLDER,
	'noplaylist': True,
}

async def _validate_context(ctx: SlashContext) -> bool:
	if ctx.author.voice is None:
		embed = discord.Embed('You need to be in a voice channel.')
		await ctx.send(embed=embed)
		return False
	
	if ctx.voice_client is None:
		await ctx.author.voice.channel.connect()
	else:
		await ctx.voice_client.move_to(ctx.author.voice.channel)
	
	return True


class MusicCog(commands.Cog):
	def __init__(self, bot: commands.Bot) -> None:
		self.bot = bot
		self.ytdl = YoutubeDL(YTDL_OPTIONS)
		self.queue = []


	@cog_ext.cog_slash()
	async def yt(self, ctx: SlashContext, link: str):
		'''
		Play music from provided youtube link.
		'''
		if not await _validate_context(ctx):
			return
		info = await self.bot.loop.run_in_executor(None, lambda: self.ytdl.extract_info(link))
		if 'entries' in info:
			info = info['entries'][0]
		
		filename = self.ytdl.prepare_filename(info)
		ctx.voice_client.play(discord.FFmpegPCMAudio(filename, options='-vn'))
		await ctx.send(f'Playing {link}')
