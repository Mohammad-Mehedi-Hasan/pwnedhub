from flask import current_app, url_for
from common import db
from common.constants import ROLES, QUESTIONS, USER_STATUSES
from common.utils import xor_encrypt, xor_decrypt, get_jaccard_sim
import datetime

class BaseModel(db.Model):
    __abstract__ = True
    id = db.Column(db.Integer, primary_key=True)
    created = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now)
    modified = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    @property
    def _name(self):
        return self.__class__.__name__.lower()

    @property
    def created_as_string(self):
        return self.created.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def modified_as_string(self):
        return self.modified.strftime("%Y-%m-%d %H:%M:%S")

class Config(db.Model):
    __tablename__ = 'configs'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    value = db.Column(db.Boolean, nullable=False)

    @staticmethod
    def get_by_name(name):
        return Config.query.filter_by(name=name).first()

    @staticmethod
    def get_value(name):
        return Config.query.filter_by(name=name).first().value

    def __repr__(self):
        return "<Config '{}'>".format(self.name)

class Note(BaseModel):
    __tablename__ = 'notes'
    name = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    def serialize(self):
        return {
            'id': self.id,
            'name': self.name,
            'content': self.content,
            'created': self.created_as_string,
            'modified': self.modified_as_string,
        }

    def __repr__(self):
        return "<Note '{}'>".format(self.name)

class Tool(BaseModel):
    __tablename__ = 'tools'
    name = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return "<Tool '{}'>".format(self.name)

class Message(BaseModel):
    __tablename__ = 'messages'
    comment = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    def serialize(self):
        return {
            'id': self.id,
            'created': self.created_as_string,
            'comment': self.comment,
            'author': {
                'id': self.user.id,
                'name': self.user.name,
                'username': self.user.username,
                'avatar': self.user.avatar_or_default,
            },
        }

    def __repr__(self):
        return "<Message '{}'>".format(self.id)

class Mail(BaseModel):
    __tablename__ = 'mail'
    subject = db.Column(db.Text, nullable=False)
    content = db.Column(db.Text, nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    read = db.Column(db.Integer, nullable=False, default=0)

    def serialize(self):
        return {
            'id': self.id,
            'created': self.created_as_string,
            'subject': self.subject,
            'content': self.content,
            'read': self.read,
            'sender': self.sender.serialize(public=True),
            'receiver': self.receiver.serialize(public=True),
        }

    def __repr__(self):
        return "<Mail '{}'>".format(self.id)

class User(BaseModel):
    __tablename__ = 'users'
    username = db.Column(db.String(255), nullable=False, unique=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    name = db.Column(db.String(255), nullable=False)
    avatar = db.Column(db.Text)
    signature = db.Column(db.Text)
    password_hash = db.Column(db.String(255))
    question = db.Column(db.Integer, nullable=False)
    answer = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.Text)
    role = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.Integer, nullable=False, default=1)
    notes = db.relationship('Note', backref='owner', lazy='dynamic')
    messages = db.relationship('Message', backref='author', lazy='dynamic')
    sent_mail = db.relationship('Mail', foreign_keys='Mail.sender_id', backref='sender', lazy='dynamic')
    received_mail = db.relationship('Mail', foreign_keys='Mail.receiver_id', backref='receiver', lazy='dynamic')

    @property
    def role_as_string(self):
        return ROLES[self.role]

    @property
    def status_as_string(self):
        return USER_STATUSES[self.status]

    @property
    def question_as_string(self):
        return QUESTIONS[self.question]

    @property
    def password_as_string(self):
        return xor_decrypt(self.password_hash, current_app.config['PW_ENC_KEY'])

    @property
    def password(self):
        raise AttributeError('password: write-only field')

    @password.setter
    def password(self, password):
        self.password_hash = xor_encrypt(password, current_app.config['PW_ENC_KEY'])

    @property
    def avatar_or_default(self):
        return self.avatar or url_for('static', filename='images/avatars/default.png')

    @property
    def is_admin(self):
        if self.role == 0:
            return True
        return False

    @property
    def is_enabled(self):
        if self.status == 1:
            return True
        return False

    @property
    def has_unread_mail(self):
        for letter in self.received_mail:
            if letter.read == 0:
                return True
        return False

    def check_password(self, password):
        if self.password_hash == xor_encrypt(password, current_app.config['PW_ENC_KEY']):
            return True
        return False

    @staticmethod
    def get_by_username(username):
        return User.query.filter_by(username=username).first()

    @staticmethod
    def get_by_email(email):
        return User.query.filter_by(email=email).first()

    def serialize(self, public=False):
        if public:
            return {
                'id': self.id,
                'created': self.created_as_string,
                'name': self.name,
                'avatar': self.avatar_or_default,
                'signature': self.signature,
            }
        return {
            'id': self.id,
            'created': self.created_as_string,
            'username': self.username,
            'email': self.email,
            'name': self.name,
            'avatar': self.avatar_or_default,
            'signature': self.signature,
            'question': self.question,
            'answer': self.answer,
            'role': self.role_as_string,
        }

    def __repr__(self):
        return "<User '{}'>".format(self.username)

class Score(BaseModel):
    __tablename__ = 'scores'
    player = db.Column(db.String(255), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    recid = db.Column(db.Integer)
    recording = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return "<Score '{}:{}'>".format(self.player, self.score)
