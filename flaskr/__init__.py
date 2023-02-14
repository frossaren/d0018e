from flask import Flask
from flask_mysqldb import MySQL
from flask import flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import MySQLdb.cursors

# create and configure the app & database connection
app = Flask(__name__)

app.secret_key = 'dev'

app.config['MYSQL_HOST']     = '130.240.200.107'
app.config['MYSQL_DB']       = 'mydb'
app.config['MYSQL_USER']     = 'external'
app.config['MYSQL_PASSWORD'] = 'password'
mysql = MySQL(app)

def get_db_cursor():
    return mysql.connection.cursor(MySQLdb.cursors.DictCursor)

def db_query(query, commit = False):
    try:
        cursor = get_db_cursor()
        cursor.execute(query)
        if commit: mysql.connection.commit()
        return cursor

    except Exception as e:
        print(f"Unable to execute query: '{query}'.\nError: {e}")
        raise Exception(e)

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None

    else:
        query = db_query(f'SELECT * FROM User WHERE id = {user_id}')
        g.user = query.fetchone()
        if g.user is None: flash("Unable to load logged in user")

@app.route('/')
def index():
    g.products = db_query("SELECT * FROM Product").fetchall()
    return render_template('index.html')

@app.route('/register/', methods=('GET', 'POST'))
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        error = None
        if not email:
            error = 'Username is required'

        elif not password:
            error = 'Password is required'

        if error is None:
            password = generate_password_hash(password)

            try:
                # Add user to db
                query = db_query(f'INSERT INTO User VALUES (NULL, "customer", "{email}", "{password}")', True)
            
                # Login user to their new account
                query = db_query(f'SELECT * FROM User WHERE email = "{email}"')
                user = query.fetchone()
                session.clear()
                session['user_id'] = user['id']
                flash("Welcome to Göstas!")

                return redirect(url_for("index"))
            
            except:
                error = f"User {email} is already registered!"

        flash(error)

    return render_template('auth/register.html')

@app.route('/login/', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Look for existing accounts
        query = db_query(f'SELECT * FROM User WHERE email = "{email}"')
        user = query.fetchone()

        error = None
        if user is None:
            error = 'Incorrect username.'

        elif not check_password_hash(user['password'], password):
            error = 'Incorrect password.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            return redirect(url_for('index'))

        flash(error)

    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()    
    return redirect(url_for('index'))

@app.route('/add_product', methods =('GET', 'POST'))
def addProduct():
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        categories = request.form['category']
        media = request.files.getlist('media')

        # Get retailer id
        try:
            s_user = session['user_id']
            query = db_query(f'SELECT id FROM Retailer WHERE account = "{s_user}"')
            retailer = query.fetchone()
            r_id = retailer['id']

        except:
            flash("No connection to retailer")
            return render_template('retailer/add_product.html')

        # Create product
        try:
            query = db_query(f'INSERT INTO Product VALUES (NULL, "{name}", {price}, {r_id}, "{categories}")', True)
        
        except:
            flash("Failed to create product")
            return render_template('retailer/add_product.html')

        # Upload media & connect to product
        try:
            query = db_query(f'SELECT LAST_INSERT_ID()')
            productId = query.fetchone()['LAST_INSERT_ID()']

            cursor = get_db_cursor() # Doesn't utilize db_query() because of item.read()
            for item in media:
                try:
                    cursor.execute('INSERT INTO Media VALUES (NULL, %s, %s)', (item.read(), productId,))
                    mysql.connection.commit()
                
                except:
                    flash("Image failed to upload")
                    pass
        
        except:
            flash("Failed to upload one or more media objects")

        flash("Successfully added product!")
        return redirect(url_for('index'))

    return render_template('retailer/add_product.html')
