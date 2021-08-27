# Discord bot entry point.
# Register and run the main logic.

import logging
import random
from argparse import ArgumentParser
from os import error

import discord
import toml
from discord.ext.commands import Bot as DiscordBot
from discord.mentions import AllowedMentions
from discord_slash import SlashCommand, SlashContext

from music import MusicCog

BOT_VERSION = '0.1.2'

bot = DiscordBot(
	'.',
	intents=discord.Intents.default(),
	allowed_mentions=AllowedMentions(users=True),
)
slash = SlashCommand(bot)
logger = logging.getLogger(__name__)


@bot.event
async def on_ready():
	logger.debug('logged in as %s (user id: %d)', bot.user.name, bot.user.id)
	logger.debug('guilds:')
	for guild in bot.guilds:
		logger.debug('%s (id: %d)', guild.name, guild.id)
	logger.info('%s is ready', bot.user.name)


@slash.slash()
async def version(ctx: SlashContext):
	'''
	Print the current bot version.
	'''
	logger.info('displaying bot version')
	await ctx.send(f"My version is `{BOT_VERSION}`.")


@slash.slash()
async def rate(ctx: SlashContext, user: discord.Member):
	'''
	Rate the provided user out of 10.
	'''
	logger.info('rating %s (id: %s)', user.display_name, user.id)
	if user.id == 305440304528359424 or user == bot.user:
		rating = 10
	else:
		rating = random.randint(1, 9)
	await ctx.send(f'{user.mention} is {rating}/10.')


def run_bot():
	# set up arguments
	parser = ArgumentParser(prog='bottica', description='Run a discord bot named "Bottica".')
	parser.add_argument('--sync', action='store_true', help='Synchronize bot commands with discord.')
	parser.add_argument('--debug-guild', type=int, help='Debug Discord Guild id to use, will override one provided in config.')
	parser.add_argument('--token', type=str, help='Discord API token to use, will override one provided in config.')
	parser.add_argument('--log', choices=('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL',))

	args = parser.parse_args()

	# parse configs
	config = {}
	try:
		config = toml.load('config.toml')
	except toml.TomlDecodeError:
		logger.error('Failed to parse "config.toml".')

	if 'token' not in config and 'token' not in args:
		print('Please provide an API token to use!')
		print('Add it to "config.toml" or provide with --token.')

	# set up logging
	log_level = args.log or config.get('log') or 0
	logging.basicConfig(
		format='%(asctime)s %(levelname)s %(name)s: %(message)s',
		level=log_level,
	)
	logger.debug('set logging level to %s', log_level)
	logging.getLogger('discord').setLevel('WARNING')

	slash.debug_guild = args.debug_guild or config.get('debug_guild')
	logger.debug('debug_guild=%s', slash.debug_guild)

	if args.sync:
		logger.info("synchronizing commands")
		bot.loop.create_task(slash.sync_all_commands())
	
	bot.add_cog(MusicCog(bot))
	bot.run(config['token'])


if __name__ == '__main__':
	run_bot()
