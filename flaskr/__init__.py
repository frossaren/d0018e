from MySQLdb import IntegrityError
from flask import Flask
from flask_mysqldb import MySQL
from flask import flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import MySQLdb.cursors
import os

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
        raise

def create_order(userId):
    query = db_query(f'INSERT INTO `Order` (userId) VALUES ({userId})', True)
    query = db_query(f'SELECT LAST_INSERT_ID()')
    order_id = query.fetchone()['LAST_INSERT_ID()']
    query = db_query(f'SELECT * FROM `Order` WHERE id = {order_id}')
    return query.fetchone()

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None

    else:
        # Load user data
        query = db_query(f'SELECT * FROM User WHERE id = {user_id}')
        g.user = query.fetchone()

        # Load cart quantity info
        try:
            query = db_query(f'SELECT id FROM `Order` WHERE userId = {user_id} AND isFinished = 0')
            order_id = query.fetchone()['id']
            query = db_query(f'SELECT COUNT(orderId) FROM CartItem WHERE orderId = {order_id}')
            g.user['cartQty'] = query.fetchone()['COUNT(orderId)']
        
        except:
            g.user['cartQty'] = 0

@app.get('/')
def index():
    g.products = db_query("SELECT * FROM Product").fetchall()
    g.prodpicscount = []
    for p in g.products:
        i = 0
        while(True):
            filepath = "flaskr/static/media/"+str(p['id'])+"_"+ str(i) +".jpg"
            if(os.path.exists(filepath)):
                i = i + 1
            else:
                g.prodpicscount.append(i)
                break
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
                query = db_query(f'SELECT id FROM User WHERE email = "{email}"')
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
        query = db_query(f'SELECT id, password FROM User WHERE email = "{email}"')
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

@app.get('/logout/')
def logout():
    session.clear()    
    return redirect(url_for('index'))

@app.route('/add_product/', methods =('GET', 'POST'))
def add_product():
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
            product_id = query.fetchone()['LAST_INSERT_ID()']

            for i in range(len(media)):
                filetype = media[i].content_type[media[i].content_type.rindex("/")+1:]
                filename = f"{product_id}_{i}.{filetype}"
                media[i].save(os.path.join(app.root_path, "static", "media", filename))
        
        except Exception as e:
            print(e)
            flash("Failed to upload one or more media objects")

        flash("Successfully added product!")
        return redirect(url_for('index'))

    return render_template('retailer/add_product.html')

# Buy button, delete from cart?
@app.route('/cart/', methods =('GET', 'POST'))
def view_cart():
    user_id = session.get('user_id')
    query = db_query(f'SELECT id, totalPrice FROM `Order` WHERE userId = {user_id} AND isFinished = 0')
    order_info = query.fetchone()

    if order_info is None:
        cart = {
            'id': "",
            'totalPrice': 0,
            'rows': ""
        }
    
    else:
        queryString = ("SELECT Product.name, Product.price, CartItem.numOrdered "
                       "FROM CartItem "
                       "INNER JOIN Product ON CartItem.productId = Product.id "
                      f'WHERE CartItem.orderId = {order_info["id"]}')
        query = db_query(queryString)
        order_rows = query.fetchall()

        cart = {
            'id': order_info['id'],
            'totalPrice': order_info['totalPrice'],
            'rows': order_rows
        }

    return render_template('cart/view_cart.html', cart = cart)

@app.post('/add_to_cart/')
def add_to_cart():
    product_id = request.form['id']
    quantity = int(request.form['qty'])

    user_id = session['user_id']

    query = db_query(f'SELECT price FROM Product WHERE id = {product_id}')
    product = query.fetchone()
    price = product['price'] * quantity

    query = db_query(f'SELECT id, totalPrice FROM `Order` WHERE userId = {user_id} AND isFinished = 0')
    curr_order = query.fetchone()

    try:
        if curr_order is None:
            # Create order
            curr_order = create_order(user_id)

        # Add to current order
        try:
            query = db_query(f'INSERT INTO CartItem VALUES ({curr_order["id"]}, {product_id}, {quantity})', True)
        
        # If cart already has product: increase amount instead
        except IntegrityError:
            query = db_query(f'SELECT numOrdered FROM CartItem WHERE orderId = {curr_order["id"]} AND productId = {product_id}')
            quantity += query.fetchone()['numOrdered']
            query = db_query(f'UPDATE CartItem SET numOrdered = {quantity} WHERE orderId = {curr_order["id"]} AND productId = {product_id}', True)

        totalPrice = curr_order['totalPrice'] + price
        query = db_query(f'UPDATE `Order` SET totalPrice = {totalPrice} WHERE id = {curr_order["id"]}', True)

    except:
        flash("Something went wrong when adding item to cart")
        return redirect(request.referrer)

    flash("Added to cart!")
    return redirect(request.referrer)

@app.post('/checkout/')
def checkout():
    user_id = session['user_id']
    query = db_query(f'SELECT id FROM `Order` WHERE userId = {user_id} AND isFinished = 0')
    curr_order = query.fetchone()
    if curr_order is None:
        flash("Nothing in cart")
        return redirect(url_for('index'))

    query = db_query(f'UPDATE `Order` SET isFinished = 1 WHERE id = {curr_order["id"]}', True)
    
    return redirect(url_for('index'))