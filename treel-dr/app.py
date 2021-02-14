import uuid
import requests
from flask import Flask, render_template, session, request, redirect, url_for, jsonify
from flask_session import Session  # https://pythonhosted.org/Flask-Session
from services.user import UserService
from services.outlook import OutlookService
from services.auth import AuthService
from loaders.loader import load
from config import REDIRECT_PATH, CONFIRMATION_PAGE_URL
from schemas.user import UserSchema
from utils import remove_none_from_dict, clean_phone_number
from datetime import datetime, timedelta

dependencies = load()
app = dependencies["app"]

@app.route("/login", methods=["POST"])
def login():
    try:
        auth_service = dependencies["auth_service"]
        session = dependencies["session"]
        # Technically we could use empty list [] as scopes to do just sign in,
        # here we choose to also collect end user consent upfront
        auth_uri = auth_service.build_auth_code_flow()
        print(request.form)
        user = UserSchema(**{
            "first": request.form["first_name"],
            "last": request.form["last_name"],
            "interval": int(request.form["interval"]),
            "phone_number": clean_phone_number(request.form["phone"]),
            "subscribed": [key for key in ["covid_updates", "job_opportunities", "school", "events"] if key in request.form]
        })
        session["user_info"] = remove_none_from_dict(user.dict())
        return redirect(auth_uri)
    except Exception as e:
        print(e)
        return jsonify({"info": "An error occured"})

@app.route(REDIRECT_PATH)  # Its absolute URL must match your app's redirect_uri set in AAD
def authorized():
    try:
        auth_service = dependencies["auth_service"]
        user_service = dependencies["user_service"]
        outlook_service = dependencies["outlook_service"]
        twilio_service = dependencies["twilio_service"]
        session = dependencies["session"]

        token = auth_service.get_access_token(request.args)

        user = outlook_service.get_user_info(token)
        user = user.dict()
        user.update(session["user_info"])
        user = UserSchema(**user)

        cache = auth_service.load_cache()

        user.token = auth_service.dumps_cache(cache)
        user.nextJob = datetime.utcnow() + timedelta(hours=user.interval)

        res = user_service.upsertUser(user)

        twilio_service.send_text(user.phone_number, f"\n🌲Welcome to TreeL;DR🌲\n\nWe will send your email digest every {user.interval} hours.\nYou are currently subscribed to emails about {(', '.join(user.subscribed))}.")

        return redirect(CONFIRMATION_PAGE_URL)
    except ValueError as e:  # Usually caused by CSRF
        return jsonify({"error": {e}})

@app.route("/graphcall/<string:email>")
def graphcall(email):
    auth_service = dependencies["auth_service"]
    user_service = dependencies["user_service"]
    outlook_service = dependencies["outlook_service"]

    user = user_service.getUser(email)
    token = auth_service.get_access_token_from_serialized(user.token)
    emails = outlook_service.get_emails(token)
    return jsonify(emails)

@app.route("/sync")
def sync():
    auth_service = dependencies["auth_service"]
    user_service = dependencies["user_service"]
    outlook_service = dependencies["outlook_service"]
    twilio_service = dependencies["twilio_service"]

    users = user_service.getUsersToProcess()

    result = []
    for user in users:
        token = auth_service.get_access_token_from_serialized(user.token)
        emails = outlook_service.get_emails(token)
        result.append({user.email: len(emails)})

        twilio_service.send_text(user.phone_number, f"\n🌲Your TreeL;DR🌲\n\nHi {user.first}!\nWe found {len(emails)} emails for you.\n\nHave a great day!\n<3 TreeL;DR")
        
        cache = auth_service.load_cache()
        user_update = UserSchema(**{
            "nextJob": datetime.utcnow() + timedelta(hours=user.interval),
            "token": auth_service.dumps_cache(cache)
        })
        user_service.updateUser(user_update, user.email)
    return jsonify(result)

if __name__ == "__main__":
    app.run(port=8000)

