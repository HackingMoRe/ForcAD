import requests
import json
from checklib import *
import re

PORT = 3000


class CheckMachine:

    def __init__(self, checker):
        self.checker = checker
        self.url = f'http://{self.checker.host}:{PORT}'
        self.prog = re.compile(r"[A-Z0-9]{31}=")

    def ping(self):
        # per il ping controlliamo che sia raggiungibile la pagina di registrazione
        r = requests.get(f'{self.url}/signup/', timeout=2)
        self.checker.check_response(r, 'Check failed')
    
    def create_user(self, session: requests.Session):

        username, password = rnd_username(), rnd_password()
        email = f"{username}@ccit.it"

        r = session.post(f"{self.url}/signup", data={"name": username, "email": email, "password": password})
        self.checker.check_response(r, 'Could not signup')
        return username, email, password
    

    def login(self, session: requests.Session, email: str, password: str):
        r = session.post(f"{self.url}/login", data={"email": email, "password": password})
        self.checker.check_response(r, 'Could not signup')

    def put_flag_1(self, flag, vuln):

        session = get_initialized_session()
        username, email, password = self.create_user(session=session)

        r = session.post(
            f"{self.url}/custom-sticker",
            data= {
                "svg": f'<svg viewBox="0 0 64.00665664672852 37.877166748046875" dominant-baseline="middle" text-anchor="middle" paint-order="stroke" stroke-linecap="butt" stroke-linejoin="round" style="filter: drop-shadow(rgb(119, 119, 119) 0px 0px 3px);"><text x="32.00332832336426" y="18.938583374023438" style="stroke: white; stroke-width: 4; font-weight: bold; fill: rgb(34, 34, 34); font-family: Pacifico;">{flag}</text></svg>',
                "qty": 1
            }
        )

        self.checker.check_response(r, 'Could not put flag')
        return email, json.dumps({"email": email, "password": password})
    
    def put_flag_2(self, flag, vuln):
        session = get_initialized_session()
        username, email, password = self.create_user(session=session)
        stickers = rnd_string(20)

        r = session.post(
            f"{self.url}/custom-sticker",
            data = {
                "svg": f'<svg viewBox="0 0 64.00665664672852 37.877166748046875" dominant-baseline="middle" text-anchor="middle" paint-order="stroke" stroke-linecap="butt" stroke-linejoin="round" style="filter: drop-shadow(rgb(119, 119, 119) 0px 0px 3px);"><text x="32.00332832336426" y="18.938583374023438" style="stroke: white; stroke-width: 4; font-weight: bold; fill: rgb(34, 34, 34); font-family: Pacifico;">{stickers}</text></svg>',
                "qty": 1
            }
        )

        r = session.post(
            f"{self.url}/cart?/buy",
            data = {
                "name": username,
                "surname": rnd_username(),
                "address": flag,
                "city": "Torino",
                "country": "Italia"
            }
        )

        self.checker.check_response(r, 'Could not put flag')
        order_id = r.json()["location"].split("/")[-1]
        return order_id, json.dumps({"email": email, "password": password, "order_id": order_id})

    def get_flag_1(self, flag_id, vuln):
        
        session, flag_id = get_initialized_session(), json.loads(flag_id)
        self.login(session, flag_id.get("email"), flag_id.get("password"))

        r = session.get(f"{self.url}/cart")
        self.checker.check_response(r, 'Could not get cart')

        flag = self.prog.search(r.text)
        self.checker.assert_(flag is not None, "Could not get flag", status=Status.CORRUPT)
        return flag.group(0)
    
    def get_flag_2(self, flag_id, vuln):
        
        session, flag_id = get_initialized_session(), json.loads(flag_id)
        self.login(session, flag_id.get("email"), flag_id.get("password"))

        r = session.get(f"{self.url}/order/{flag_id.get('order_id')}")
        self.checker.check_response(r, 'Could not get cart')

        flag = self.prog.search(r.text)
        self.checker.assert_(flag is not None, "Could not get flag", status=Status.CORRUPT)
        return flag.group(0)