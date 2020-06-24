from flask import Blueprint, current_app, request, session, g, redirect, url_for, render_template, flash, jsonify, Response, send_file, abort, __version__
from sqlalchemy import asc, desc
from sqlalchemy.sql import func
from pwnedhub import db
from pwnedhub.decorators import login_required, roles_required, validate, csrf_protect
from common.models import Config, Mail, Message, Tool, Bug, User, Score
from common.constants import ROLES, QUESTIONS, DEFAULT_NOTE, ADMIN_RESPONSE, VULNERABILITIES, SEVERITY, BUG_STATUSES, REVIEW_NOTIFICATION, UPDATE_NOTIFICATION, BUG_NOTIFICATIONS
from common.utils import unfurl_url
from common.validators import is_valid_password, is_valid_command, is_valid_filename, is_valid_mimetype
from datetime import datetime
from lxml import etree
from urllib.parse import urlencode
import math
import os
import re
import subprocess

core = Blueprint('core', __name__)

#@core.before_app_request
#def render_mobile():
#    if any(x in request.user_agent.string.lower() for x in ['android', 'iphone', 'ipad']):
#        if not request.endpoint.startswith('static'):
#            return render_template('spa.html')

@core.before_app_request
def load_user():
    g.user = None
    if session.get('user_id'):
        g.user = User.query.get(session.get('user_id'))

@core.after_app_request
def add_header(response):
    response.headers['X-Powered-By'] = 'Flask/{}'.format(__version__)
    return response

@core.after_app_request
def restrict_flashes(response):
    flashes = session.get('_flashes')
    if flashes and len(flashes) > 5:
        del session['_flashes'][0]
    return response

# general controllers

@core.route('/')
def index():
    return render_template('index.html')

@core.route('/home')
def home():
    if g.user.is_admin:
        return redirect(url_for('core.admin_users'))
    return redirect(url_for('core.notes'))

@core.route('/about')
def about():
    return render_template('about.html')

# admin controllers

@core.route('/admin/tools')
@login_required
@roles_required('admin')
def admin_tools():
    tools = Tool.query.order_by(Tool.name.asc()).all()
    return render_template('admin_tools.html', tools=tools)

@core.route('/admin/tools/add', methods=['POST'])
@login_required
@roles_required('admin')
@validate(['name', 'path', 'description'])
def admin_tools_add():
    tool = Tool(
        name=request.form['name'],
        path=request.form['path'],
        description=request.form['description'],
    )
    db.session.add(tool)
    db.session.commit()
    flash('Tool added.')
    return redirect(url_for('core.admin_tools'))

@core.route('/admin/tools/remove/<int:tid>')
@login_required
@roles_required('admin')
def admin_tools_remove(tid):
    tool = Tool.query.get_or_404(tid)
    db.session.delete(tool)
    db.session.commit()
    flash('Tool removed.')
    return redirect(url_for('core.admin_tools'))

@core.route('/admin/users')
@login_required
@roles_required('admin')
def admin_users():
    users = User.query.filter(User.id != g.user.id).order_by(User.username.asc()).all()
    return render_template('admin_users.html', users=users)

@core.route('/admin/users/<string:action>/<int:uid>')
@login_required
def admin_users_modify(action, uid):
    user = User.query.get_or_404(uid)
    if user != g.user:
        if action == 'promote':
            user.role = 0
            db.session.add(user)
            db.session.commit()
            flash('User promoted.')
        elif action == 'demote':
            user.role = 1
            db.session.add(user)
            db.session.commit()
            flash('User demoted.')
        elif action == 'enable':
            user.status = 1
            db.session.add(user)
            db.session.commit()
            flash('User enabled.')
        elif action == 'disable':
            user.status = 0
            db.session.add(user)
            db.session.commit()
            flash('User disabled.')
        else:
            flash('Invalid user action.')
    else:
        flash('Self-modification denied.')
    return redirect(url_for('core.admin_users'))

@core.route('/config', methods=['GET', 'POST'])
def config():
    # simulate the latency of an external API request
    import time
    time.sleep(0.25)
    # hide the existence of this route if not an admin
    if not g.user or ROLES[g.user.role] != ROLES[0]:
        return abort(404)
    if request.method == 'POST':
        Config.get_by_name('CSRF_PROTECT').value = request.form.get('csrf_protect') == 'on' or False
        Config.get_by_name('BEARER_AUTH_ENABLE').value = request.form.get('bearer_enable') == 'on' or False
        Config.get_by_name('CORS_RESTRICT').value = request.form.get('cors_restrict') == 'on' or False
        Config.get_by_name('OIDC_ENABLE').value = request.form.get('oidc_enable') == 'on' or False
        db.session.commit()
        flash('Configuration updated')
    return render_template('config.html')

# user controllers

@core.route('/profile', methods=['GET', 'POST'])
@login_required
@validate(['name', 'question', 'answer'])
@csrf_protect
def profile():
    user = g.user
    if request.values:
        password = request.values['password']
        if password:
            if is_valid_password(password):
                user.password = password
            else:
                flash('Password does not meet complexity requirements.')
        user.avatar = request.values['avatar']
        user.signature = request.values['signature']
        user.name = request.values['name']
        user.question = request.values['question']
        user.answer = request.values['answer']
        db.session.add(user)
        db.session.commit()
        flash('Account information changed.')
    return render_template('profile.html', user=user, questions=QUESTIONS)

@core.route('/profile/view/<int:uid>')
@login_required
def profile_view(uid):
    user = User.query.get_or_404(uid)
    return render_template('profile_view.html', user=user)

@core.route('/mail')
@login_required
def mail():
    mail = g.user.received_mail.order_by(Mail.created.desc()).all()
    return render_template('mail_inbox.html', mail=mail)

@core.route('/mail/compose', methods=['GET', 'POST'])
@login_required
@validate(['receiver', 'subject', 'content'])
def mail_compose():
    if request.method == 'POST':
        receiver = User.query.get(request.form['receiver'])
        if not receiver:
            abort(400, 'Invalid receiver.')
        content = request.form['content']
        subject = request.form['subject']
        letter = Mail(content=content, subject=subject, sender=g.user, receiver=receiver)
        db.session.add(letter)
        db.session.commit()
        # generate automated Administrator response
        if receiver.role == 0:
            content = ADMIN_RESPONSE
            letter = Mail(content=content, subject='RE: '+subject, sender=receiver, receiver=g.user)
            db.session.add(letter)
            db.session.commit()
        flash('Mail sent.')
        return redirect(url_for('core.mail'))
    users = User.query.filter(User.id != g.user.id).order_by(User.username.asc()).all()
    return render_template('mail_compose.html', users=users)

@core.route('/mail/reply/<int:mid>')
@login_required
def mail_reply(mid=0):
    letter = Mail.query.get_or_404(mid)
    return render_template('mail_reply.html', letter=letter)

@core.route('/mail/view/<int:mid>')
@login_required
def mail_view(mid):
    letter = Mail.query.get_or_404(mid)
    if letter.read == 0:
        letter.read = 1
        db.session.add(letter)
        db.session.commit()
    return render_template('mail_view.html', letter=letter)

@core.route('/mail/delete/<int:mid>')
@login_required
def mail_delete(mid):
    letter = Mail.query.get_or_404(mid)
    db.session.delete(letter)
    db.session.commit()
    flash('Mail deleted.')
    return redirect(url_for('core.mail'))

@core.route('/messages')
@core.route('/messages/page/<int:page>')
@login_required
def messages(page=1):
    messages = Message.query.order_by(Message.created.desc()).paginate(page=page, per_page=5)
    return render_template('messages.html', messages=messages)

@core.route('/messages/create', methods=['POST'])
@login_required
@validate(['message'])
def messages_create():
    message = request.form['message']
    msg = Message(comment=message, user=g.user)
    db.session.add(msg)
    db.session.commit()
    return redirect(url_for('core.messages'))

@core.route('/messages/delete/<int:mid>')
@login_required
def messages_delete(mid):
    message = Message.query.get_or_404(mid)
    if message.user == g.user or g.user.is_admin:
        db.session.delete(message)
        db.session.commit()
        flash('Message deleted.')
    else:
        abort(403)
    return redirect(url_for('core.messages'))

@core.route('/messages/unfurl', methods=['POST'])
def unfurl():
    url = request.json.get('url')
    headers = {'User-Agent': request.headers.get('User-Agent')}
    data = {'error': 'RequestError', 'message': 'Invalid request.'}
    status = 400
    if url:
        try:
            data = unfurl_url(url, headers)
            status = 200
        except Exception as e:
            data = {'error': 'UnfurlError', 'message': str(e)}
            status = 500
    return jsonify(**data), status

@core.route('/notes')
@login_required
@roles_required('user')
def notes():
    notes = g.user.notes or DEFAULT_NOTE
    return render_template('notes.html', notes=notes)

@core.route('/notes', methods=['PUT'])
@login_required
@roles_required('user')
def notes_update():
    g.user.notes = request.json.get('notes')
    db.session.add(g.user)
    db.session.commit()
    return jsonify(notes=g.user.notes)

@core.route('/artifacts')
@login_required
@roles_required('user')
def artifacts():
    artifacts = []
    for (dirpath, dirnames, filenames) in os.walk(session.get('upload_folder')):
        valid_filenames = [f for f in filenames if is_valid_filename(f)]
        for filename in valid_filenames:
            modified_ts = os.path.getmtime(os.path.join(dirpath, filename))
            modified = datetime.fromtimestamp(modified_ts).strftime('%Y-%m-%d %H:%M:%S')
            artifacts.append({'filename': filename, 'modified': modified})
        break
    return render_template('artifacts.html', artifacts=artifacts)

@core.route('/artifacts/save', methods=['POST'])
@login_required
@roles_required('user')
@validate(['file'])
def artifacts_save():
    file = request.files['file']
    if is_valid_filename(file.filename):
        if is_valid_mimetype(file.mimetype):
            path = os.path.join(session.get('upload_folder'), file.filename)
            if not os.path.isfile(path):
                try:
                    file.save(path)
                except IOError:
                    flash('Unable to save the artifact.')
            else:
                flash('An artifact with that name already exists.')
        else:
            flash('Invalid file type. Only {} types allowed.'.format(', '.join(current_app.config['ALLOWED_MIMETYPES'])))
    else:
        flash('Invalid file extension. Only {} extensions allowed.'.format(', '.join(current_app.config['ALLOWED_EXTENSIONS'])))
    return redirect(url_for('core.artifacts'))

@core.route('/artifacts/create', methods=['POST'])
@login_required
@roles_required('user')
def artifacts_create():
    xml = request.data
    parser = etree.XMLParser(no_network=False)
    doc = etree.fromstring(xml, parser)
    content = doc.find('content').text
    filename = doc.find('filename').text
    if all((content, filename)):
        filename += '-{}.txt'.format(datetime.now().strftime('%s'))
        msg = 'Artifact created \'{}\'.'.format(filename)
        path = os.path.join(session.get('upload_folder'), filename)
        if not os.path.isfile(path):
            try:
                with open(path, 'w') as fp:
                    fp.write(content)
            except IOError:
                msg = 'Unable to save as an artifact.'
        else:
            msg = 'An artifact with that name already exists.'
    else:
        msg = 'Invalid request.'
    xml = '<xml><message>{}</message></xml>'.format(msg)
    return Response(xml, mimetype='application/xml')

@core.route('/artifacts/delete', methods=['POST'])
@login_required
@roles_required('user')
@validate(['filename'])
def artifacts_delete():
    filename = request.form['filename']
    try:
        os.remove(os.path.join(session.get('upload_folder'), filename))
        flash('Artifact deleted.')
    except IOError:
        flash('Unable to remove the artifact.')
    return redirect(url_for('core.artifacts'))

@core.route('/artifacts/view', methods=['POST'])
@login_required
@roles_required('user')
@validate(['filename'])
def artifacts_view():
    filename = request.form['filename']
    try:
        return send_file(os.path.join(session.get('upload_folder'), filename))
    except IOError:
        flash('Unable to load the artifact.')
    return redirect(url_for('core.artifacts'))

@core.route('/tools')
@login_required
@roles_required('user')
def tools():
    tools = Tool.query.all()
    return render_template('tools.html', tools=tools)

@core.route('/tools/info/<string:tid>', methods=['GET'])
@login_required
@roles_required('user')
def tools_info(tid):
    query = 'SELECT * FROM tools WHERE id='+tid
    try:
        tool = db.session.execute(query).first() or {}
    except:
        tool = {}
    return jsonify(**dict(tool))

@core.route('/tools/execute/<string:tid>', methods=['POST'])
@login_required
@roles_required('user')
def tools_execute(tid):
    tool = Tool.query.get_or_404(tid)
    path = tool.path
    args = request.json.get('args')
    cmd = '{} {}'.format(path, args)
    error = False
    if is_valid_command(cmd):
        env = os.environ.copy()
        env['PATH'] = os.pathsep.join(('/usr/bin', env['PATH']))
        p = subprocess.Popen([cmd, args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, env=env)
        out, err = p.communicate()
        output = (out + err).decode()
    else:
        output = 'Command contains invalid characters.'
        error = True
    return jsonify(cmd=cmd, output=output, error=error)

@core.route('/submissions')
@core.route('/submissions/page/<int:page>')
@login_required
def submissions(page=1):
    submissions = Bug.query.order_by(Bug.created.desc()).paginate(page=page, per_page=10)
    return render_template('submissions.html', submissions=submissions)

@core.route('/submissions/new', methods=['GET', 'POST'])
@login_required
@roles_required('user')
@validate(['title', 'vuln_id', 'severity', 'description', 'impact'])
def submissions_new():
    if request.method == 'POST':
        title = request.form['title']
        vuln_id = request.form['vuln_id']
        severity = request.form['severity']
        description = request.form['description']
        impact = request.form['impact']
        signature = ' '.join((title, description, impact))
        if Bug.is_unique(signature):
            # only basic users can be reviewers
            reviewer = User.query.filter(
                User.id != g.user.id,
                User.status == 1,
                User.role == 1,
            ).order_by(func.random()).first()
            submission = Bug(
                title=title,
                vuln_id=vuln_id,
                severity=severity,
                description=description,
                impact=impact,
                submitter=g.user,
                reviewer=reviewer
            )
            # send message to reviewer
            sender = User.query.get(1)
            receiver = reviewer
            subject = 'New Submission for Review'
            bug_href = url_for('core.submissions_view', bid=submission.id, _external=True)
            content = REVIEW_NOTIFICATION.format(bug_href, submission.id)
            mail = Mail(content=content, subject=subject, sender=sender, receiver=receiver)
            db.session.add(submission)
            db.session.add(mail)
            db.session.commit()
            flash('Submission created.')
            return redirect(url_for('core.submissions_view', bid=submission.id))
        else:
            flash('Similar submission already exists.')
    return render_template('submissions_new.html', vulnerabilities=VULNERABILITIES, severity=SEVERITY)

@core.route('/submissions/edit/<int:bid>', methods=['GET', 'POST'])
@login_required
@roles_required('user')
@validate(['title', 'vuln_id', 'severity', 'description', 'impact'])
def submissions_edit(bid):
    submission = Bug.query.get_or_404(bid)
    if submission.is_validated or submission.submitter != g.user:
        abort(403)
    if request.method == 'POST':
        submission.title = request.form['title']
        submission.vuln_id = request.form['vuln_id']
        submission.severity = request.form['severity']
        submission.description = request.form['description']
        submission.impact = request.form['impact']
        # send message to reviewer
        sender = User.query.get(1)
        receiver = submission.reviewer
        subject = 'Submission Updated'
        bug_href = url_for('core.submissions_view', bid=submission.id, _external=True)
        content = UPDATE_NOTIFICATION.format(bug_href, submission.id)
        mail = Mail(content=content, subject=subject, sender=sender, receiver=receiver)
        db.session.add(submission)
        db.session.add(mail)
        db.session.commit()
        flash('Submission updated.')
        return redirect(url_for('core.submissions_view', bid=submission.id))
    return render_template('submissions_edit.html', submission=submission, vulnerabilities=VULNERABILITIES, severity=SEVERITY)

@core.route('/submissions/view/<int:bid>')
@login_required
def submissions_view(bid):
    submission = Bug.query.get_or_404(bid)
    return render_template('submissions_view.html', submission=submission)

@core.route('/submissions/<string:action>/<int:bid>')
@login_required
@roles_required('user')
def submissions_action(action, bid):
    submission = Bug.query.get_or_404(bid)
    if submission.is_validated or submission.reviewer != g.user:
        abort(403)
    if [status for status in BUG_STATUSES.values() if status.startswith(action)]:
        # passing previous check guarantees at least one result
        submission.status = [aid for aid, status in BUG_STATUSES.items() if status.startswith(action)][0]
        # send message to submitter
        sender = User.query.get(1)
        receiver = submission.submitter
        subject = 'Submission #{:05d} {}'.format(submission.id, BUG_STATUSES[submission.status].title())
        bug_href = url_for('core.submissions_view', bid=submission.id, _external=True)
        if submission.status == 1:
            content = BUG_NOTIFICATIONS[submission.status].format(bug_href, submission.id)
        if submission.status == 2:
            content = BUG_NOTIFICATIONS[submission.status].format(bug_href, submission.id, submission.bounty)
        if submission.status == 3:
            content = BUG_NOTIFICATIONS[submission.status].format(bug_href, submission.id)
        mail = Mail(content=content, subject=subject, sender=sender, receiver=receiver)
        db.session.add(submission)
        db.session.add(mail)
        db.session.commit()
        flash('Bug status changed.')
    else:
        flash('Invalid action.')
    return redirect(url_for('core.submissions_view', bid=bid))

@core.route('/bounty/scoreboard')
@login_required
def bounty_scoreboard():
    # only basic users populate the scoreboard
    users = User.query.filter(User.role == 1).all()
    bug_data = sorted(users, key=lambda user: user.bugs.count(), reverse=True)
    validation_data = sorted(users, key=lambda user: len(user.completed_validations), reverse=True)
    omission_data = sorted(users, key=lambda user: len(user.open_validations), reverse=True)
    return render_template('bounty_scoreboard.html', users=users, bug_data=bug_data, validation_data=validation_data, omission_data=omission_data)

@core.route('/bounty/info')
@login_required
@roles_required('user')
def bounty_info():
    return render_template('bounty_info.html')

@core.route('/games')
@login_required
def games():
    return render_template('games.html')

@core.route('/snake/<path:filename>')
@login_required
def snake_files(filename):
    rec_regex = r'rec(\d+)\.txt'
    if filename == 'highscores.txt':
        scores = Score.query.filter(Score.recid != None).order_by(Score.recid).all()
        scoreboard = []
        for i in range(0, len(scores)):
            scoreboard.append(('name'+str(i), scores[i].player))
            scoreboard.append(('score'+str(i), scores[i].score))
            scoreboard.append(('recFile'+str(i), scores[i].recid))
        return urlencode(scoreboard)
    elif re.search(rec_regex, filename):
        recid = re.search(rec_regex, filename).group(1)
        score = Score.query.filter_by(recid=recid).first()
        if not score:
            abort(404)
        return score.recording
    abort(404)

@core.route('/snake/enterHighscore.php', methods=['POST'])
@login_required
def snake_enter_score():
    status = 'no response'
    # make sure scorehash is correct for the given score
    score = int(request.form['score'])
    scorehash = int(request.form['scorehash'])
    if math.sqrt(scorehash - 1337) == score:
        if request.form['SNAKE_BLOCK'] == '1':
            # create recording string
            recTurn = request.form['recTurn']
            recFrame = request.form['recFrame']
            recFood = request.form['recFood']
            recData = urlencode({ 'recTurn':recTurn, 'recFrame':recFrame, 'recFood':recFood })
            # add the new score
            playerName = g.user.username#request.form['playerName']#re.sub('[&=#<>]', '', request.form['playerName'])
            score = Score(player=playerName, score=score, recording=recData)
            db.session.add(score)
            db.session.commit()
            # reset the high scores. the game requests rec#.txt files 0-9 by
            # default, so the recid field must be updated for the high scores
            # clear out current high scores
            for score in Score.query.all():
                score.recid = None
                db.session.add(score)
            db.session.commit()
            # update the recid field to set the new high scores
            scores = Score.query.order_by(Score.score.desc()).limit(10).all()
            for i in range(0, len(scores)):
                scores[i].recid = i
                db.session.add(scores[i])
            db.session.commit()
            status = 'ok'
        else:
            status = 'snake block not present'
    else:
        status = 'invalid scorehash'
    return urlencode({'status':status})
