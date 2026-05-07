import requests
from django.conf import settings

_token = None


def get_eskiz_token():
    global _token
    response = requests.post('https://notify.eskiz.uz/api/auth/login', data={
        'email': settings.ESKIZ_EMAIL,
        'password': settings.ESKIZ_PASSWORD,
    })
    _token = response.json()['data']['token']
    return _token


def send_sms(phone: str, message: str) -> bool:
    """
    Sends SMS via Eskiz.uz. Returns True on success, False otherwise.
    Never raises — always returns bool.
    """
    try:
        token = get_eskiz_token()
        response = requests.post(
            'https://notify.eskiz.uz/api/message/sms/send',
            headers={'Authorization': f'Bearer {token}'},
            data={
                'mobile_phone': phone.replace('+', ''),
                'message': message,
                'from': '4546',
            },
            timeout=10,
        )
        return response.status_code == 200
    except Exception:
        return False
