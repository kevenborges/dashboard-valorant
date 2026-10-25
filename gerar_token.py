import requests

client_id = 'isbtkqx3z958wgqkgrhfu4tu6hjbyj'
client_secret = '3f5651xjw3t8f2sdcca39ie8u991m2'

url = 'https://id.twitch.tv/oauth2/token'
parametros = {
    'client_id': client_id,
    'client_secret': client_secret,
    'grant_type': 'client_credentials'
}

resposta = requests.post(url, data=parametros)
print(f"O teu TWITCH_TOKEN é: {resposta.json().get('access_token')}")