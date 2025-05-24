from . import db # Import the db instance from app/__init__.py
from datetime import datetime
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON # Using SQLite's JSON type
# from sqlalchemy import JSON # Generic JSON type, might need specific dialect for some DBs
from sqlalchemy import Text # Fallback if JSON type causes issues, store as JSON string
import json # For to_dict method if storing complex objects as strings

class ArbitrageRecord(db.Model):
    __tablename__ = 'arbitrage_record'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Storing complex path and solution details as JSON strings in Text columns
    # This is broadly compatible. For SQLite, db.JSON can also be used if preferred
    # and the SQLite version supports it well with Flask-SQLAlchemy.
    # Using Text for wider compatibility initially. If SQLite JSON features are needed, can switch.
    opportunity_path_json = db.Column(Text, nullable=False) 
    optimized_solution_json = db.Column(Text, nullable=True)
    
    status = db.Column(db.String(100), nullable=False) # e.g., "opportunity_found", "simulated_execution_success"
    
    expected_profit_estimate = db.Column(db.Float, nullable=True)
    actual_profit = db.Column(db.Float, nullable=True) # To be filled if real execution happens
    
    notes = db.Column(db.Text, nullable=True) # For errors, additional info, or context

    def __repr__(self):
        return f"<ArbitrageRecord id={self.id} status='{self.status}' timestamp='{self.timestamp.isoformat()}'>"

    def to_dict(self):
        """Serializes the ArbitrageRecord object to a dictionary."""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() + 'Z', # ISO format with Z for UTC
            'opportunity_path': json.loads(self.opportunity_path_json) if self.opportunity_path_json else None,
            'optimized_solution': json.loads(self.optimized_solution_json) if self.optimized_solution_json else None,
            'status': self.status,
            'expected_profit_estimate': self.expected_profit_estimate,
            'actual_profit': self.actual_profit,
            'notes': self.notes
        }
```
