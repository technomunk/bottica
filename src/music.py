# Music-playing Cog for the bot

import logging
import random
import traceback
from collections import deque
from os import path
from typing import Sequence

import discord
from discord.ext import commands
from discord_slash import SlashContext, cog_ext
from youtube_dl import YoutubeDL

import response

DATA_FOLDER = 'data/'
CACHE_FOLDER = DATA_FOLDER + 'cache/'

logger = logging.Logger(__name__)


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
	def __init__(self, bot: commands.Bot, verbose = False) -> None:
		self.bot = bot
		ytdl_options = {
			'format': 'bestaudio',
			'outtmpl': CACHE_FOLDER + '%(title)s-%(id)s.%(ext)s',
			'cachedir': DATA_FOLDER + 'dlcache',
			'download_archive': DATA_FOLDER + 'dlarchive.txt',
			'ignoreerrors': True,
			'quiet': not verbose,
		}
		self.ytdl = YoutubeDL(ytdl_options)
		self.queue = deque()
		self.voice_client = None
		self.is_shuffling = False
		self.verbose = verbose


	async def _queue_audio(self, infos: Sequence[dict]):
		if self.is_shuffling:
			# pick a random url and process it first, keeping the rest in order
			idx = random.randrange(1, len(infos))
			infos[0], infos[idx] = infos[idx], infos[0]

		for info in infos:
			filename = self.ytdl.prepare_filename(info)
			if path.exists(filename):
				self.queue.append(filename)
			else:
				url = info['url']
				# download should be run asynchronously as to avoid blocking the bot
				info = await self.bot.loop.run_in_executor(None, lambda: self.ytdl.extract_info(url))
				if not info:
					logger.warn(f'skipping {url} because it could not be downloaded!')
					continue
				self.queue.append(filename)
				if not self.is_playing():
					self.play_next()


	def is_playing(self):
		return self.voice_client is not None and self.voice_client.is_playing()


	@cog_ext.cog_slash()
	async def play(self, ctx: SlashContext, query: str):
		'''
		Play provided input.
		'''
		logger.info('playing %s', query)
		try:
			if not await _validate_context(ctx):
				return
			self.voice_client = ctx.voice_client
			# download should be run asynchronously as to avoid blocking the bot
			info = await self.bot.loop.run_in_executor(
				None,
				lambda: self.ytdl.extract_info(query, download=False, process=False),
			)
			if info:
				await ctx.send(random.choice(response.SUCCESSES))
			else:
				return await ctx.send(random.choice(response.FAILS))


			if 'entries' in info:
				await self._queue_download([entry['url'] for entry in info['entries']])
			else:
				await self._queue_download((info['url'],))

			# actual playing will happen once audio is available
		except Exception as e:
			traceback.print_exception(type(e), e, e.__traceback__)
	

	@cog_ext.cog_slash()
	async def shuffle(self, ctx: SlashContext):
		'''
		Toggle shuffling of the queued playlist.
		'''
		logger.info('toggling shuffle')
		self.is_shuffling = not self.is_shuffling
		if self.is_shuffling:
			resp = 'Shuffling queued songs.'
		else:
			resp = 'Playing queued songs in order.'
		await ctx.send(resp)
	

	@cog_ext.cog_slash()
	async def next(self, ctx: SlashContext):
		'''
		Skip the current song.
		'''
		logger.info('skipping song')
		if not self.is_playing():
			return await ctx.send("I'm not playing anything." + random.choice(response.FAILS))
		
		self.play_next()
		await ctx.send(random.choice(response.SUCCESSES))
	

	def play_next(self):
		'''
		Play the next song in the queue.
		'''
		if self.voice_client is None or self.voice_client.channel is None:
			raise RuntimeError("Bot is not connected to voice to play.")
		
		if not self.queue:
			return
		
		if not self.voice_client.is_connected():
			return logger.warn('Client is not connected!')
		
		if self.is_shuffling:
			idx = random.randrange(len(self.queue))
			file = self.queue[idx]
			del self.queue[idx]
		else:
			file = self.queue.popleft()
		
		if not file:
			return logger.warn('Attempted to play an empty file!')
		
		if self.is_playing():
			self.voice_client.pause()
		
		def handle_after(error):
			if error is None:
				self.play_next()
			else:
				logger.error('encountered error: %s', error)
		
		self.voice_client.play(discord.FFmpegPCMAudio(file, options='-vn'), after=handle_after)
		logger.debug('playing %s', file)
