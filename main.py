import os
from flask import Flask, redirect, url_for, session, request, render_template, flash
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from functools import wraps
from threading import Thread
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.environ.get('FLASK_SECRET', 'segredosuperseguro@123')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Configuração Flask-Mail via ENV ---
app.config.update(
    MAIL_SERVER=os.environ.get('MAIL_SERVER'),
    MAIL_PORT=int(os.environ.get('MAIL_PORT', 465)),
    MAIL_USE_SSL=True,
    MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD'),
)
mail = Mail(app)

db = SQLAlchemy(app)

# --- Definição de modelos ---
class Denuncia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.Text, nullable=False)
    data_hora = db.Column(db.DateTime, server_default=db.func.now())

# --- Criação automática das tabelas no import ---
with app.app_context():
    db.create_all()

# --- Função para carregar e-mails autorizados do arquivo ---
def carregar_emails_autorizados(arquivo='autorizados.txt'):
    if not os.path.exists(arquivo):
        return []
    with open(arquivo, 'r', encoding='utf-8') as f:
        return [linha.strip().lower() for linha in f if linha.strip()]

EMAILS_AUTORIZADOS = carregar_emails_autorizados()

# --- Funções de envio assíncrono de e-mail ao RH ---
def _send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

def notify_rh(texto_denuncia):
    rh_email = os.environ.get('RH_EMAIL')
    if not rh_email:
        return
    msg = Message(
        subject='Nova denúncia recebida',
        sender=app.config['MAIL_USERNAME'],
        recipients=[rh_email],
        body=f"Uma nova denúncia foi registrada:\n\n{texto_denuncia}"
    )
    Thread(target=_send_async_email, args=(app, msg)).start()

# --- Decorator de acesso restrito ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get('user')
        if not user or user['email'].lower() not in EMAILS_AUTORIZADOS:
            flash('Acesso restrito apenas para usuários autorizados.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Rotas ---
@app.route('/')
@login_required
def index():
    return redirect(url_for('denuncia'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].lower()
        if email in EMAILS_AUTORIZADOS:
            session['user'] = {'email': email}
            return redirect(url_for('denuncia'))
        else:
            flash('E-mail não autorizado.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/denuncia', methods=['GET', 'POST'])
@login_required
def denuncia():
    if request.method == 'POST':
        texto = request.form['texto']
        db.session.add(Denuncia(texto=texto))
        db.session.commit()
        # envia e-mail ao RH
        notify_rh(texto)
        flash('Denúncia enviada com sucesso!')
        return redirect(url_for('denuncia'))
    return render_template('denuncia.html')

@app.route('/admin')
@login_required
def admin():
    user = session.get('user')
    if user['email'].lower() != os.environ.get('ADMIN_EMAIL', '').lower():
        return redirect(url_for('login'))
    denuncias = Denuncia.query.order_by(Denuncia.data_hora.desc()).all()
    return render_template('admin.html', denuncias=denuncias)

# bloco __main__ só para debug local
if __name__ == "__main__":
    app.run(debug=True)
