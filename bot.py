# Discord bot entry point.
# Register and run the main logic.

import discord
from discord_slash import SlashCommand, SlashContext

BOT_VERSION = '0.0.0'

bot = discord.Client(intents=discord.Intents.default())
# when developing add 'sync_commands=True' and 'debug_guild=<guild id>'
slash = SlashCommand(bot)

@bot.event
async def on_ready():
	print(f'Logged in as {bot.user.name}.')
	print(f'User id: {bot.user.id}')
	print('Guilds:')
	for guild in bot.guilds:
		print(f'{guild.name} (id: {guild.id})')


@slash.slash()
async def version(ctx: SlashContext):
	'''
	Print the current bot version.
	'''
	await ctx.send(f"My version is `{BOT_VERSION}`.")


def run_bot():
	token = ''
	try:
		with open('.token') as token_file:
			token = token_file.readline()
	except FileNotFoundError:
		print('Please create a ".token" file with a bot token to use.')
		return
	bot.run(token)


if __name__ == '__main__':
	run_bot()
