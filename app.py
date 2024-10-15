from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from functools import wraps
import os
from collections import defaultdict

# Initialize the database
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    
    # Load the configuration directly
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://easyMeals:Jdn%40z%29PA73nBsxuB@localhost/easymeal2'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_default_secret_key')
    app.config['SPOONACULAR_API_KEY'] = os.environ.get('SPOONACULAR_API_KEY', 'aa4a1ccfb226475e8fcc87389f849d14')

    # Initialize the database with the app
    db.init_app(app)
    
    return app

# Create the application instance
app = create_app()

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

# Favorite model
class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipe_id = db.Column(db.Integer, nullable=False)

# ShoppingList model
class ShoppingList(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ingredient = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Helper function to get recipe details from Spoonacular API
def get_recipe_details(recipe_id):
    url = f'https://api.spoonacular.com/recipes/{recipe_id}/information'
    params = {'apiKey': app.config['SPOONACULAR_API_KEY'], 'includeNutrition': True}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        app.logger.error(f"Error fetching recipe {recipe_id}: {str(e)}")
        return None

# Home route
@app.route('/')
def home():
    url = 'https://api.spoonacular.com/recipes/random'
    params = {'apiKey': app.config['SPOONACULAR_API_KEY'], 'number': 1}
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        random_recipe = response.json().get('recipes', [])
        if random_recipe:
            return render_template('home.html', recipe=random_recipe[0])
    return render_template('home.html', error="Couldn't fetch a random recipe")

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            return redirect(url_for('home'))
        return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')

# Register route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return render_template('register.html', error="Username already exists")
        new_user = User(username=username, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

# Logout route
@app.route('/logout')
@login_required
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

# Search route
@app.route('/search')
def search():
    return render_template('search.html')

# Search API route
@app.route('/api/search')
def api_search():
    query = request.args.get('query', '')
    url = 'https://api.spoonacular.com/recipes/complexSearch'
    params = {'apiKey': app.config['SPOONACULAR_API_KEY'], 'query': query, 'number': 10}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return jsonify(response.json())
    return jsonify({'error': 'Failed to fetch recipes'}), 500

# Recipe route
@app.route('/recipe/<int:recipe_id>')
@login_required
def recipe_detail(recipe_id):
    recipe = get_recipe_details(recipe_id)
    
    if recipe is None:
        app.logger.error(f"Failed to fetch recipe details for ID: {recipe_id}")
        return "Recipe not found", 404

    is_favorite = Favorite.query.filter_by(user_id=session['user_id'], recipe_id=recipe_id).first() is not None

    return render_template(
        'recipe.html',
        recipe=recipe,
        recipe_id=recipe_id,
        is_favorite=is_favorite
    )

# Add to favorites route
@app.route('/add_favorite', methods=['POST'])
@login_required
def add_favorite():
    data = request.get_json()
    recipe_id = data.get('recipe_id')
    
    if not recipe_id:
        return jsonify({'status': 'error', 'message': 'recipe_id is required'}), 400

    existing_favorite = Favorite.query.filter_by(user_id=session['user_id'], recipe_id=recipe_id).first()
    
    if not existing_favorite:
        new_favorite = Favorite(user_id=session['user_id'], recipe_id=recipe_id)
        db.session.add(new_favorite)
        db.session.commit()
        return jsonify({'status': 'success'})
    
    return jsonify({'status': 'already_favorited'})

# Remove from favorites route
@app.route('/remove_favorite/<int:recipe_id>', methods=['POST'])
@login_required
def remove_favorite(recipe_id):
    favorite = Favorite.query.filter_by(user_id=session['user_id'], recipe_id=recipe_id).first()
    if favorite:
        db.session.delete(favorite)
        db.session.commit()
    return jsonify({'status': 'success'})

# Favorites route
@app.route('/favourites')
@login_required
def favorites():
    user_favorites = Favorite.query.filter_by(user_id=session['user_id']).all()
    favorite_recipes = []
    for fav in user_favorites:
        recipe_details = get_recipe_details(fav.recipe_id)
        if recipe_details:
            favorite_recipes.append(recipe_details)
    return render_template('favourites.html', recipes=favorite_recipes)

# Add to shopping list route
@app.route('/add_to_shopping_list', methods=['POST'])
@login_required
def add_to_shopping_list():
    data = request.json
    for item in data['ingredients']:
        existing_item = ShoppingList.query.filter_by(
            user_id=session['user_id'],
            ingredient=item['original'],  
            unit=item.get('unit', '')
        ).first()
        if existing_item:
            existing_item.quantity += item.get('amount', 1)
        else:
            new_item = ShoppingList(
                user_id=session['user_id'],
                ingredient=item['original'],
                quantity=item.get('amount', 1),
                unit=item.get('unit', '')
            )
            db.session.add(new_item)
    db.session.commit()
    return jsonify({'status': 'success'})

# Shopping list route
@app.route('/shopping_list')
@login_required
def shopping_list():
    user_favorites = Favorite.query.filter_by(user_id=session['user_id']).all()
    ingredients = defaultdict(float)
    
    for fav in user_favorites:
        recipe_details = get_recipe_details(fav.recipe_id)
        if recipe_details and 'extendedIngredients' in recipe_details:
            for ingredient in recipe_details['extendedIngredients']:
            # Initialize variables
                quantity = 0
                unit = None
            
            # Check if 'originalString' exists
            if 'originalName' in ingredient:
                quantity, unit, name = parse_ingredient(ingredient['originalName'])
                key = f"{name}_{unit}"
                
                # Only update ingredients if key is valid
                if key:  # Ensure key is not None or empty
                    ingredients[key] += quantity
            else:
                # Handle the case where 'originalString' is missing
                print(f"Missing 'name' for ingredient: {ingredient}")

    return render_template('shopping_list.html', ingredients=ingredients)

def parse_ingredient(ingredient):
    """Helper function to parse ingredients into (quantity, unit, name)."""
    # Parse logic based on known structures
    return 1, '', ingredient  # Simplified, improve by actual parsing logic.

if __name__ == '__main__':
    app.run(debug=True)
