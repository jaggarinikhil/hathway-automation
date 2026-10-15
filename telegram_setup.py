"""Local Telegram setup; secrets are prompted privately, never printed or saved."""
import argparse
import getpass
from telegram_notify import post


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command', choices=['ids','register','info'])
    args=parser.parse_args()
    token=getpass.getpass('Telegram bot token (hidden): ')
    base='https://api.telegram.org/bot'+token+'/'
    try:
        if args.command=='ids':
            data=post(base+'getUpdates', {'allowed_updates':['message']})
            for update in data.get('result',[]):
                message=update.get('message',{})
                if message.get('chat',{}).get('type')=='private':
                    print('User ID:',message.get('from',{}).get('id'),'Chat ID:',message['chat']['id'])
        elif args.command=='register':
            url=input('Worker HTTPS base URL: ').strip().rstrip('/')
            if not url.startswith('https://'):raise ValueError('HTTPS required')
            secret=getpass.getpass('TELEGRAM_WEBHOOK_SECRET (hidden): ')
            data=post(base+'setWebhook', {'url':url+'/telegram/webhook','secret_token':secret,
                                         'allowed_updates':['message'],'max_connections':1,
                                         'drop_pending_updates':True})
            print('Webhook registered:',data.get('ok') is True)
        else:
            data=post(base+'getWebhookInfo',{})
            info=data.get('result',{})
            print('Webhook URL:',info.get('url'))
            print('Pending updates:',info.get('pending_update_count'))
            print('Last error:',info.get('last_error_message','none'))
    except Exception:
        print('Telegram setup failed. Check token, connectivity, and existing webhook; no token was printed.')
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
