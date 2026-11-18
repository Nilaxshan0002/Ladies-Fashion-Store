from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Category, Product, CartItem, Order, OrderItem
from functools import wraps

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fashion.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'ladies-fashion-secret-key-change-me'
db.init_app(app)


# ---------- Decorators ----------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access only.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_cart_count():
    count = 0
    if 'user_id' in session:
        count = sum(i.quantity for i in CartItem.query.filter_by(user_id=session['user_id']).all())
    return {'cart_count': count}


# ---------- Home / Shop ----------
@app.route('/')
def index():
    featured = Product.query.order_by(Product.id.desc()).limit(6).all()
    categories = Category.query.all()
    return render_template('index.html', featured=featured, categories=categories)


@app.route('/shop')
def shop():
    category_id = request.args.get('category', type=int)
    search = request.args.get('q', '')
    query = Product.query
    if category_id:
        query = query.filter_by(category_id=category_id)
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    products = query.order_by(Product.id.desc()).all()
    categories = Category.query.all()
    return render_template('shop.html', products=products, categories=categories,
                           active_cat=category_id, search=search)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    related = Product.query.filter_by(category_id=product.category_id).filter(
        Product.id != product_id).limit(4).all()
    return render_template('product.html', product=product, related=related)


# ---------- Auth ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'danger')
            return redirect(url_for('register'))
        db.session.add(User(username=username,
                            password=generate_password_hash(password),
                            role='customer'))
        db.session.commit()
        flash('Account created. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('login.html', mode='register')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username'].strip()).first()
        if user and check_password_hash(user.password, request.form['password']):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            flash(f'Welcome, {user.username}!', 'success')
            return redirect(url_for('index'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html', mode='login')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'success')
    return redirect(url_for('index'))


# ---------- Cart ----------
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    qty = int(request.form.get('quantity', 1))
    existing = CartItem.query.filter_by(user_id=session['user_id'],
                                        product_id=product_id).first()
    if existing:
        existing.quantity += qty
    else:
        db.session.add(CartItem(user_id=session['user_id'],
                                product_id=product_id, quantity=qty))
    db.session.commit()
    flash(f'{product.name} added to cart.', 'success')
    return redirect(request.referrer or url_for('shop'))


@app.route('/cart')
@login_required
def cart():
    items = CartItem.query.filter_by(user_id=session['user_id']).all()
    total = sum(i.product.price * i.quantity for i in items)
    return render_template('cart.html', items=items, total=total)


@app.route('/cart/remove/<int:item_id>')
@login_required
def remove_from_cart(item_id):
    item = CartItem.query.get_or_404(item_id)
    if item.user_id == session['user_id']:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for('cart'))


@app.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    item = CartItem.query.get_or_404(item_id)
    if item.user_id == session['user_id']:
        qty = int(request.form['quantity'])
        if qty > 0:
            item.quantity = qty
            db.session.commit()
        else:
            db.session.delete(item)
            db.session.commit()
    return redirect(url_for('cart'))


# ---------- Checkout / Orders ----------
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    items = CartItem.query.filter_by(user_id=session['user_id']).all()
    if not items:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('shop'))
    total = sum(i.product.price * i.quantity for i in items)
    if request.method == 'POST':
        order = Order(user_id=session['user_id'], total=total,
                      address=request.form['address'],
                      phone=request.form['phone'], status='Pending')
        db.session.add(order)
        db.session.flush()
        for i in items:
            db.session.add(OrderItem(
                order_id=order.id, product_id=i.product_id,
                product_name=i.product.name, price=i.product.price,
                quantity=i.quantity))
            db.session.delete(i)
        db.session.commit()
        flash('Order placed successfully!', 'success')
        return redirect(url_for('orders'))
    return render_template('checkout.html', items=items, total=total)


@app.route('/orders')
@login_required
def orders():
    my_orders = Order.query.filter_by(user_id=session['user_id']).order_by(Order.id.desc()).all()
    return render_template('orders.html', orders=my_orders)


# ---------- Admin ----------
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    products = Product.query.order_by(Product.id.desc()).all()
    orders = Order.query.order_by(Order.id.desc()).all()
    users = User.query.all()
    return render_template('admin.html', products=products, orders=orders, users=users)


@app.route('/admin/add_product', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    categories = Category.query.all()
    if request.method == 'POST':
        p = Product(
            name=request.form['name'],
            description=request.form.get('description', ''),
            price=float(request.form['price']),
            size=request.form.get('size', ''),
            color=request.form.get('color', ''),
            stock=int(request.form.get('stock', 0)),
            image_url=request.form.get('image_url', ''),
            category_id=request.form.get('category_id') or None
        )
        db.session.add(p)
        db.session.commit()
        flash('Product added.', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('add_product.html', categories=categories)


@app.route('/admin/edit_product/<int:pid>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(pid):
    p = Product.query.get_or_404(pid)
    categories = Category.query.all()
    if request.method == 'POST':
        p.name = request.form['name']
        p.description = request.form.get('description', '')
        p.price = float(request.form['price'])
        p.size = request.form.get('size', '')
        p.color = request.form.get('color', '')
        p.stock = int(request.form.get('stock', 0))
        p.image_url = request.form.get('image_url', '')
        p.category_id = request.form.get('category_id') or None
        db.session.commit()
        flash('Product updated.', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('add_product.html', categories=categories, product=p)


@app.route('/admin/delete_product/<int:pid>')
@login_required
@admin_required
def delete_product(pid):
    p = Product.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    flash('Product deleted.', 'info')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/order/<int:oid>/<status>')
@login_required
@admin_required
def update_order(oid, status):
    if status not in ['Pending', 'Shipped', 'Delivered', 'Cancelled']:
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_dashboard'))
    o = Order.query.get_or_404(oid)
    o.status = status
    db.session.commit()
    flash('Order updated.', 'success')
    return redirect(url_for('admin_dashboard'))


# ---------- Boot ----------
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin',
                            password=generate_password_hash('admin123'),
                            role='admin'))
    if Category.query.count() == 0:
        cats = [Category(name='Dresses'), Category(name='Tops'),
                Category(name='Skirts'), Category(name='Accessories')]
        db.session.add_all(cats)
        db.session.commit()
    if Product.query.count() == 0:
        dresses = Category.query.filter_by(name='Dresses').first().id
        tops = Category.query.filter_by(name='Tops').first().id
        skirts = Category.query.filter_by(name='Skirts').first().id
        acc = Category.query.filter_by(name='Accessories').first().id
        db.session.add_all([
            Product(name='Floral Summer Dress', price=4500, size='S,M,L',
                    color='Blue', stock=15, category_id=dresses,
                    image_url='https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=500',
                    description='Light and breezy floral dress perfect for summer.'),
            Product(name='Elegant Evening Gown', price=12000, size='S,M,L,XL',
                    color='Black', stock=8, category_id=dresses,
                    image_url='https://images.unsplash.com/photo-1566174053879-31528523f8ae?w=500',
                    description='Stunning floor-length gown for special occasions.'),
            Product(name='Silk Blouse', price=3200, size='S,M,L',
                    color='Cream', stock=20, category_id=tops,
                    image_url='https://images.unsplash.com/photo-1564257577460-7a1eb1f9d3d8?w=500',
                    description='Soft silk blouse with elegant drape.'),
            Product(name='Pleated Midi Skirt', price=2800, size='S,M,L',
                    color='Beige', stock=12, category_id=skirts,
                    image_url='https://images.unsplash.com/photo-1583496661160-fb5886a0aaaa?w=500',
                    description='Classic pleated midi skirt with flattering fit.'),
            Product(name='Pearl Necklace', price=1800, size='One Size',
                    color='White', stock=25, category_id=acc,
                    image_url='https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?w=500',
                    description='Elegant pearl necklace for any outfit.'),
            Product(name='Leather Handbag', price=5500, size='One Size',
                    color='Brown', stock=10, category_id=acc,
                    image_url='https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=500',
                    description='Genuine leather handbag with gold hardware.'),
        ])
    db.session.commit()


if __name__ == '__main__':
    app.run(debug=True)