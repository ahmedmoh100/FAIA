"""
Response Cache Manager for FAIA
Implements hybrid caching (Memory + Database) with semantic similarity for chat responses
"""

import hashlib
import json
import time
import logging
from collections import OrderedDict
from functools import wraps
from typing import Optional, Dict, Any, List
import sys
from pathlib import Path
import re
import gzip
import base64

# Add database integration
admin_backend_path = Path(__file__).resolve().parent.parent.parent / "admin" / "backend"
if str(admin_backend_path) not in sys.path:
    sys.path.insert(0, str(admin_backend_path))

from config import engine
from sqlalchemy import text

logger = logging.getLogger(__name__)


class SemanticSimilarity:
    """Simple semantic similarity for cache key matching"""
    
    def __init__(self):
        # Common question patterns and their normalized forms
        self.question_patterns = {
            # AI/ML related - more comprehensive patterns
            r'\b(what is|what does|explain|tell me about|define|describe)\s+(ai|artificial intelligence)\b': 'what_is_ai',
            r'\b(ai|artificial intelligence)\s+(mean|means)\b': 'what_is_ai',
            r'\b(about|regarding)\s+(ai|artificial intelligence)\b': 'what_is_ai',
            r'\b(what is|explain|tell me about|define)\s+(ml|machine learning)\b': 'what_is_ml',
            r'\b(what is|explain|tell me about|define)\s+(neural network|nn)\b': 'what_is_neural_network',
            r'\b(what is|explain|tell me about|define)\s+(deep learning|dl)\b': 'what_is_deep_learning',
            
            # Programming & Computer Science
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(python|programming)\b': 'what_is_python',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(javascript|js)\b': 'what_is_javascript',
            r'\b(how to|how do i)\s+(code|program|write)\b': 'how_to_code',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(algorithm|algorithms)\b': 'what_is_algorithm',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(data structure|data structures)\b': 'what_is_data_structure',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(computer science|cs)\b': 'what_is_computer_science',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(software engineering|se)\b': 'what_is_software_engineering',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(database|databases|sql)\b': 'what_is_database',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(cybersecurity|security)\b': 'what_is_cybersecurity',
            
            # Mathematics & Statistics
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(mathematics|math|maths)\b': 'what_is_mathematics',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(statistics|stats)\b': 'what_is_statistics',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(calculus)\b': 'what_is_calculus',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(linear algebra|algebra)\b': 'what_is_algebra',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(probability)\b': 'what_is_probability',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(discrete math|discrete mathematics)\b': 'what_is_discrete_math',
            
            # Natural Sciences
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(physics)\b': 'what_is_physics',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(chemistry)\b': 'what_is_chemistry',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(biology)\b': 'what_is_biology',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(biochemistry)\b': 'what_is_biochemistry',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(molecular biology)\b': 'what_is_molecular_biology',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(genetics)\b': 'what_is_genetics',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(environmental science)\b': 'what_is_environmental_science',
            
            # Engineering
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(engineering)\b': 'what_is_engineering',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(mechanical engineering)\b': 'what_is_mechanical_engineering',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(electrical engineering)\b': 'what_is_electrical_engineering',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(civil engineering)\b': 'what_is_civil_engineering',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(chemical engineering)\b': 'what_is_chemical_engineering',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(biomedical engineering)\b': 'what_is_biomedical_engineering',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(aerospace engineering)\b': 'what_is_aerospace_engineering',
            
            # Business & Economics
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(business|business administration)\b': 'what_is_business',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(economics)\b': 'what_is_economics',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(finance)\b': 'what_is_finance',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(accounting)\b': 'what_is_accounting',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(marketing)\b': 'what_is_marketing',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(management)\b': 'what_is_management',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(entrepreneurship)\b': 'what_is_entrepreneurship',
            
            # Social Sciences
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(psychology)\b': 'what_is_psychology',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(sociology)\b': 'what_is_sociology',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(anthropology)\b': 'what_is_anthropology',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(political science|politics)\b': 'what_is_political_science',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(international relations)\b': 'what_is_international_relations',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(criminology)\b': 'what_is_criminology',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(social work)\b': 'what_is_social_work',
            
            # Humanities & Liberal Arts
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(literature|english literature)\b': 'what_is_literature',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(history)\b': 'what_is_history',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(philosophy)\b': 'what_is_philosophy',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(linguistics)\b': 'what_is_linguistics',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(art history)\b': 'what_is_art_history',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(creative writing)\b': 'what_is_creative_writing',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(journalism)\b': 'what_is_journalism',
            
            # Health & Medical Sciences
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(medicine|medical science)\b': 'what_is_medicine',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(nursing)\b': 'what_is_nursing',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(pharmacy)\b': 'what_is_pharmacy',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(public health)\b': 'what_is_public_health',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(dentistry)\b': 'what_is_dentistry',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(veterinary medicine)\b': 'what_is_veterinary_medicine',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(physical therapy|physiotherapy)\b': 'what_is_physical_therapy',
            
            # Arts & Design
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(fine arts|art)\b': 'what_is_fine_arts',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(graphic design)\b': 'what_is_graphic_design',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(architecture)\b': 'what_is_architecture',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(music)\b': 'what_is_music',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(theater|theatre)\b': 'what_is_theater',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(film studies|cinema)\b': 'what_is_film_studies',
            
            # Education & Communication
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(education)\b': 'what_is_education',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(communications|communication)\b': 'what_is_communications',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(media studies)\b': 'what_is_media_studies',
            
            # Law & Legal Studies
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(law|legal studies)\b': 'what_is_law',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(criminal justice)\b': 'what_is_criminal_justice',
            
            # Environmental & Earth Sciences
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(geology)\b': 'what_is_geology',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(geography)\b': 'what_is_geography',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(meteorology)\b': 'what_is_meteorology',
            
            # Study Methods & Academic Skills
            r'\b(how to|how do i)\s+(study|learn)\b': 'how_to_study',
            r'\b(how to|how do i)\s+(write|research|essay)\b': 'how_to_research',
            r'\b(what is|what does|explain|tell me about|define|describe|about|regarding)\s+(research methodology)\b': 'what_is_research_methodology',
            
            # General patterns
            r'\b(hello|hi|hey)\b': 'greeting',
            r'\b(help|assist|support)\b': 'help_request',
            r'\b(thank you|thanks|thx)\b': 'thanks',
            r'\b(bye|goodbye|see you)\b': 'goodbye'
        }
        
        # Compile patterns for efficiency
        self.compiled_patterns = {
            re.compile(pattern, re.IGNORECASE): normalized 
            for pattern, normalized in self.question_patterns.items()
        }
    
    def normalize_question(self, question: str) -> str:
        """Normalize question to find semantic matches"""
        question_lower = question.lower().strip()
        
        # Remove common filler words and phrases
        filler_words = [
            'please', 'can you', 'could you', 'would you', 'i want to know', 
            'tell me', 'i want to', 'help me', 'let me know', 'i need to know'
        ]
        for filler in filler_words:
            question_lower = question_lower.replace(filler, '').strip()
        
        # Normalize common variations
        replacements = {
            # Technology
            'artificial intelligence': 'ai',
            'machine learning': 'ml',
            'neural network': 'nn',
            'deep learning': 'dl',
            'computer science': 'cs',
            'software engineering': 'se',
            
            # Sciences
            'mathematics': 'math',
            'statistics': 'stats',
            'biochemistry': 'biochem',
            'molecular biology': 'molbio',
            'environmental science': 'enviro',
            
            # Engineering
            'mechanical engineering': 'mech eng',
            'electrical engineering': 'elec eng',
            'civil engineering': 'civil eng',
            'chemical engineering': 'chem eng',
            'biomedical engineering': 'biomed eng',
            'aerospace engineering': 'aero eng',
            
            # Business
            'business administration': 'business',
            'international relations': 'intl relations',
            
            # Health Sciences
            'veterinary medicine': 'vet med',
            'physical therapy': 'pt',
            'physiotherapy': 'pt',
            
            # Arts
            'fine arts': 'art',
            'graphic design': 'design',
            'film studies': 'film',
            'theatre': 'theater',
            
            # Other
            'english literature': 'literature',
            'criminal justice': 'criminology',
            'media studies': 'communications'
        }
        for old, new in replacements.items():
            question_lower = question_lower.replace(old, new)
        
        # Check against patterns
        for pattern, normalized in self.compiled_patterns.items():
            if pattern.search(question_lower):
                return normalized
        
        # If no pattern matches, use simplified version
        # Remove punctuation and extra spaces
        simplified = re.sub(r'[^\w\s]', '', question_lower)
        simplified = re.sub(r'\s+', ' ', simplified).strip()
        
        # Take first 5 significant words (ignore very short words)
        words = [w for w in simplified.split() if len(w) > 2][:5]
        return '_'.join(words) if words else simplified
    
    def get_similarity_score(self, q1: str, q2: str) -> float:
        """Advanced similarity score with multiple algorithms"""
        # Normalize both questions
        norm1 = self.normalize_question(q1)
        norm2 = self.normalize_question(q2)
        
        # Exact normalized match
        if norm1 == norm2:
            return 1.0
        
        # Multiple similarity algorithms
        scores = []
        
        # 1. Domain-specific similarity
        domain_score = self._get_domain_similarity(q1, q2)
        scores.append(domain_score)
        
        # 2. Jaccard similarity (word overlap)
        jaccard_score = self._get_jaccard_similarity(norm1, norm2)
        scores.append(jaccard_score)
        
        # 3. N-gram similarity
        ngram_score = self._get_ngram_similarity(q1, q2)
        scores.append(ngram_score)
        
        # 4. Semantic structure similarity
        structure_score = self._get_structure_similarity(q1, q2)
        scores.append(structure_score)
        
        # Weighted combination of scores
        weights = [0.4, 0.3, 0.2, 0.1]  # Domain > Jaccard > N-gram > Structure
        final_score = sum(score * weight for score, weight in zip(scores, weights))
        
        return min(final_score, 1.0)  # Cap at 1.0
    
    def _get_domain_similarity(self, q1: str, q2: str) -> float:
        """Domain-specific similarity scoring"""
        q1_lower = q1.lower()
        q2_lower = q2.lower()
        
        # Define domain clusters
        domains = {
            # Technology & Computer Science
            'ai': ['ai', 'artificial intelligence', 'machine intelligence'],
            'ml': ['ml', 'machine learning', 'learning algorithm'],
            'dl': ['deep learning', 'neural network', 'deep neural'],
            'programming': ['programming', 'coding', 'code', 'python', 'javascript', 'software'],
            'algorithm': ['algorithm', 'sorting', 'searching', 'complexity'],
            'data': ['data structure', 'array', 'list', 'tree', 'graph', 'database'],
            'computer_science': ['computer science', 'cs', 'software engineering', 'cybersecurity'],
            
            # Mathematics & Statistics
            'mathematics': ['mathematics', 'math', 'maths', 'calculus', 'algebra', 'geometry'],
            'statistics': ['statistics', 'stats', 'probability', 'data analysis'],
            'discrete_math': ['discrete math', 'discrete mathematics', 'combinatorics'],
            
            # Natural Sciences
            'physics': ['physics', 'quantum', 'mechanics', 'thermodynamics', 'electromagnetism'],
            'chemistry': ['chemistry', 'organic', 'inorganic', 'biochemistry', 'molecular'],
            'biology': ['biology', 'genetics', 'molecular biology', 'cell biology', 'ecology'],
            'environmental': ['environmental science', 'ecology', 'climate', 'sustainability'],
            
            # Engineering
            'engineering': ['engineering', 'mechanical', 'electrical', 'civil', 'chemical'],
            'mechanical_eng': ['mechanical engineering', 'thermodynamics', 'mechanics'],
            'electrical_eng': ['electrical engineering', 'electronics', 'circuits'],
            'civil_eng': ['civil engineering', 'construction', 'structural'],
            'biomedical_eng': ['biomedical engineering', 'medical devices', 'biotechnology'],
            
            # Business & Economics
            'business': ['business', 'management', 'administration', 'entrepreneurship'],
            'economics': ['economics', 'microeconomics', 'macroeconomics', 'finance'],
            'finance': ['finance', 'accounting', 'investment', 'banking'],
            'marketing': ['marketing', 'advertising', 'branding', 'sales'],
            
            # Social Sciences
            'psychology': ['psychology', 'cognitive', 'behavioral', 'mental health'],
            'sociology': ['sociology', 'social', 'society', 'culture'],
            'anthropology': ['anthropology', 'cultural', 'archaeological'],
            'political_science': ['political science', 'politics', 'government', 'policy'],
            'international_relations': ['international relations', 'diplomacy', 'foreign policy'],
            'criminology': ['criminology', 'criminal justice', 'law enforcement'],
            
            # Humanities & Liberal Arts
            'literature': ['literature', 'english', 'poetry', 'novels', 'creative writing'],
            'history': ['history', 'historical', 'ancient', 'modern', 'medieval'],
            'philosophy': ['philosophy', 'ethics', 'logic', 'metaphysics'],
            'linguistics': ['linguistics', 'language', 'grammar', 'syntax'],
            'journalism': ['journalism', 'media', 'news', 'reporting'],
            
            # Health & Medical Sciences
            'medicine': ['medicine', 'medical', 'healthcare', 'clinical'],
            'nursing': ['nursing', 'patient care', 'healthcare'],
            'pharmacy': ['pharmacy', 'pharmaceutical', 'drugs', 'medication'],
            'public_health': ['public health', 'epidemiology', 'health policy'],
            'dentistry': ['dentistry', 'dental', 'oral health'],
            'veterinary': ['veterinary', 'animal health', 'veterinary medicine'],
            
            # Arts & Design
            'fine_arts': ['fine arts', 'art', 'painting', 'sculpture', 'visual arts'],
            'design': ['graphic design', 'design', 'visual design', 'ui', 'ux'],
            'architecture': ['architecture', 'architectural', 'building design'],
            'music': ['music', 'musical', 'composition', 'performance'],
            'theater': ['theater', 'theatre', 'drama', 'acting'],
            'film': ['film', 'cinema', 'movie', 'filmmaking'],
            
            # Education & Communication
            'education': ['education', 'teaching', 'pedagogy', 'learning'],
            'communications': ['communications', 'communication', 'media studies'],
            
            # Law & Legal Studies
            'law': ['law', 'legal', 'jurisprudence', 'legal studies'],
            
            # Earth Sciences
            'geology': ['geology', 'earth science', 'rocks', 'minerals'],
            'geography': ['geography', 'spatial', 'cartography', 'gis'],
            'meteorology': ['meteorology', 'weather', 'climate', 'atmospheric'],
            
            # General interaction
            'greeting': ['hello', 'hi', 'hey', 'good morning', 'good afternoon'],
            'help': ['help', 'assist', 'support', 'guide', 'explain'],
            'thanks': ['thank', 'thanks', 'appreciate', 'grateful']
        }
        
        # Find domains for each question
        q1_domains = set()
        q2_domains = set()
        
        for domain, terms in domains.items():
            for term in terms:
                if term in q1_lower:
                    q1_domains.add(domain)
                if term in q2_lower:
                    q2_domains.add(domain)
        
        # Calculate domain overlap
        if q1_domains and q2_domains:
            intersection = q1_domains.intersection(q2_domains)
            union = q1_domains.union(q2_domains)
            return len(intersection) / len(union) if union else 0.0
        
        return 0.0
    
    def _get_jaccard_similarity(self, norm1: str, norm2: str) -> float:
        """Jaccard similarity with improvements"""
        words1 = set(norm1.split('_'))
        words2 = set(norm2.split('_'))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _get_ngram_similarity(self, q1: str, q2: str, n: int = 2) -> float:
        """N-gram similarity for character-level matching"""
        def get_ngrams(text: str, n: int) -> set:
            text = text.lower().replace(' ', '')
            return set(text[i:i+n] for i in range(len(text) - n + 1))
        
        ngrams1 = get_ngrams(q1, n)
        ngrams2 = get_ngrams(q2, n)
        
        if not ngrams1 or not ngrams2:
            return 0.0
        
        intersection = ngrams1.intersection(ngrams2)
        union = ngrams1.union(ngrams2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _get_structure_similarity(self, q1: str, q2: str) -> float:
        """Structural similarity (question patterns)"""
        # Question type patterns
        question_patterns = {
            'what': r'\bwhat\b',
            'how': r'\bhow\b',
            'why': r'\bwhy\b',
            'when': r'\bwhen\b',
            'where': r'\bwhere\b',
            'explain': r'\bexplain\b',
            'define': r'\bdefine\b',
            'tell': r'\btell\b'
        }
        
        q1_patterns = set()
        q2_patterns = set()
        
        for pattern_name, pattern in question_patterns.items():
            if re.search(pattern, q1.lower()):
                q1_patterns.add(pattern_name)
            if re.search(pattern, q2.lower()):
                q2_patterns.add(pattern_name)
        
        if q1_patterns and q2_patterns:
            intersection = q1_patterns.intersection(q2_patterns)
            union = q1_patterns.union(q2_patterns)
            return len(intersection) / len(union) if union else 0.0
        
        return 0.0


class LRUCache:
    """LRU (Least Recently Used) Cache implementation"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        """
        Initialize LRU cache
        
        Args:
            max_size: Maximum number of items to cache
            ttl: Time to live in seconds (default 1 hour)
        """
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache"""
        if key not in self.cache:
            self.misses += 1
            return None
        
        # Check if expired
        item = self.cache[key]
        if time.time() - item['timestamp'] > self.ttl:
            del self.cache[key]
            self.misses += 1
            return None
        
        # Move to end (most recently used)
        self.cache.move_to_end(key)
        self.hits += 1
        return item['data']
    
    def set(self, key: str, value: Any):
        """Set item in cache with LRU eviction"""
        # Remove oldest item if at capacity
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)
        
        self.cache[key] = {
            'data': value,
            'timestamp': time.time()
        }
        self.cache.move_to_end(key)
    
    def clear(self):
        """Clear entire cache"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        logger.info("Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': round(hit_rate, 2),
            'ttl': self.ttl
        }


class DatabaseCache:
    """Database-backed persistent cache using XAMPP MySQL"""
    
    def __init__(self, table_name: str = "response_cache"):
        import re
        # Validate table name to avoid SQL injection via table name
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', table_name):
            raise ValueError("Invalid table_name")
        self.table_name = table_name
        self.engine = engine
        self._ensure_table_exists()
        logger.info("Database cache initialized with table: %s", table_name)
    
    def _ensure_table_exists(self):
        """Create cache table if it doesn't exist"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS {} (
                        cache_key VARCHAR(255) PRIMARY KEY,
                        cache_type VARCHAR(50) DEFAULT 'general',
                        cache_data LONGTEXT NOT NULL,
                        expires_at DATETIME NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        hit_count INT DEFAULT 0,
                        INDEX idx_expires (expires_at),
                        INDEX idx_type (cache_type)
                    )
                """.format(self.table_name)))
                conn.commit()
                logger.info("Cache table %s ready", self.table_name)
        except Exception as e:
            logger.error("Error creating cache table: %s", e)
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from database cache with decompression"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT cache_data, expires_at, hit_count, cache_type
                    FROM {} 
                    WHERE cache_key = :key AND expires_at > NOW()
                """.format(self.table_name)), {"key": key})
                
                row = result.fetchone()
                if row:
                    cache_data_str, expires_at, hit_count, cache_type = row
                    
                    # Update hit count
                    conn.execute(text("""
                        UPDATE {} 
                        SET hit_count = hit_count + 1 
                        WHERE cache_key = :key
                    """.format(self.table_name)), {"key": key})
                    conn.commit()
                    
                    # Decompress if needed
                    if cache_type and cache_type.endswith('_compressed'):
                        try:
                            compressed_data = base64.b64decode(cache_data_str.encode('utf-8'))
                            cache_data_str = gzip.decompress(compressed_data).decode('utf-8')
                        except Exception as e:
                            logger.error("Error decompressing cache data: %s", e)
                            return None
                    
                    # Deserialize data
                    return json.loads(cache_data_str)
                
                return None
        except Exception as e:
            logger.error("Error getting from database cache: %s", e)
            return None
    
    def set(self, key: str, value: Any, cache_type: str, ttl: int = 3600):
        """Set item in database cache with compression"""
        try:
            with self.engine.connect() as conn:
                # Serialize data
                cache_data = json.dumps(value, default=str)
                
                # Compress if data is large (>1KB)
                if len(cache_data) > 1024:
                    compressed_data = gzip.compress(cache_data.encode('utf-8'))
                    cache_data = base64.b64encode(compressed_data).decode('utf-8')
                    cache_type = f"{cache_type}_compressed"
                
                # Calculate expiry time
                expires_at = f"DATE_ADD(NOW(), INTERVAL {ttl} SECOND)"
                
                # Insert or update
                conn.execute(text("""
                    INSERT INTO {} 
                    (cache_key, cache_type, cache_data, expires_at)
                    VALUES (:key, :cache_type, :cache_data, {expires_at})
                    ON DUPLICATE KEY UPDATE
                    cache_data = VALUES(cache_data),
                    expires_at = VALUES(expires_at),
                    created_at = CURRENT_TIMESTAMP,
                    hit_count = 0
                """.format(self.table_name)), {
                    "key": key,
                    "cache_type": cache_type,
                    "cache_data": cache_data
                })
                conn.commit()
        except Exception as e:
            logger.error("Error setting database cache: %s", e)
    

    
    def delete(self, key: str) -> bool:
        """Delete item from database cache"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    DELETE FROM {} WHERE cache_key = :key
                """.format(self.table_name)), {"key": key})
                conn.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error("Error deleting from database cache: %s", e)
            return False
    # clear_expired removed - unused function
    # clear_by_type removed - unused function
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database cache statistics"""
        try:
            with self.engine.connect() as conn:
                # Get overall stats
                result = conn.execute(text("""
                    SELECT 
                        COUNT(*) as total_entries,
                        SUM(hit_count) as total_hits,
                        AVG(hit_count) as avg_hits,
                        COUNT(CASE WHEN expires_at <= NOW() THEN 1 END) as expired_entries
                    FROM {}
                """.format(self.table_name)))
                row = result.fetchone()
                
                # Get stats by type
                type_result = conn.execute(text("""
                    SELECT cache_type, COUNT(*) as count, SUM(hit_count) as hits
                    FROM {}
                    WHERE expires_at > NOW()
                    GROUP BY cache_type
                """.format(self.table_name)))
                
                by_type = {}
                for type_row in type_result:
                    by_type[type_row[0]] = {
                        "count": type_row[1],
                        "hits": type_row[2]
                    }
                
                return {
                    "total_entries": row[0] or 0,
                    "total_hits": row[1] or 0,
                    "avg_hits": round(row[2] or 0, 2),
                    "expired_entries": row[3] or 0,
                    "by_type": by_type
                }
        except Exception as e:
            logger.error("Error getting database cache stats: %s", e)
            return {"total_entries": 0, "total_hits": 0, "avg_hits": 0, "expired_entries": 0, "by_type": {}}


class ResponseCacheManager:
    """Advanced hybrid caching system with semantic similarity, adaptive TTL, and cache warming"""
    
    def __init__(self):
        # L1 Cache: Memory (fast access)
        self.chat_cache = LRUCache(max_size=500, ttl=1800)  # 30 min for chat
        self.rag_cache = LRUCache(max_size=200, ttl=3600)   # 1 hour for RAG
        self.db_cache = LRUCache(max_size=1000, ttl=300)    # 5 min for DB
        
        # L2 Cache: Database (persistent)
        self.db_cache_backend = DatabaseCache("response_cache")
        
        # Semantic similarity for smart caching
        self.semantic_similarity = SemanticSimilarity()
        
        # Cache statistics
        self.l1_hits = 0
        self.l2_hits = 0
        self.semantic_hits = 0
        self.misses = 0
        self.warm_hits = 0
        
        # Cache warming data - expanded for university subjects
        self.common_questions = [
            # Technology & Computer Science
            "What is artificial intelligence?",
            "What is AI?", 
            "Explain machine learning",
            "What is ML?",
            "How does neural network work?",
            "What is deep learning?",
            "What is programming?",
            "How to learn Python?",
            "What is algorithm?",
            "What is data structure?",
            "What is computer science?",
            "What is software engineering?",
            "What is cybersecurity?",
            "What is database?",
            
            # Mathematics & Statistics
            "What is mathematics?",
            "What is calculus?",
            "What is statistics?",
            "What is linear algebra?",
            "What is probability?",
            "What is discrete mathematics?",
            
            # Natural Sciences
            "What is physics?",
            "What is chemistry?",
            "What is biology?",
            "What is biochemistry?",
            "What is genetics?",
            "What is environmental science?",
            
            # Engineering
            "What is engineering?",
            "What is mechanical engineering?",
            "What is electrical engineering?",
            "What is civil engineering?",
            "What is chemical engineering?",
            "What is biomedical engineering?",
            
            # Business & Economics
            "What is business?",
            "What is economics?",
            "What is finance?",
            "What is accounting?",
            "What is marketing?",
            "What is management?",
            
            # Social Sciences
            "What is psychology?",
            "What is sociology?",
            "What is anthropology?",
            "What is political science?",
            "What is international relations?",
            "What is criminology?",
            
            # Humanities & Liberal Arts
            "What is literature?",
            "What is history?",
            "What is philosophy?",
            "What is linguistics?",
            "What is journalism?",
            
            # Health & Medical Sciences
            "What is medicine?",
            "What is nursing?",
            "What is pharmacy?",
            "What is public health?",
            "What is dentistry?",
            
            # Arts & Design
            "What is fine arts?",
            "What is graphic design?",
            "What is architecture?",
            "What is music?",
            "What is theater?",
            
            # Education & Law
            "What is education?",
            "What is law?",
            "What is communications?",
            
            # Earth Sciences
            "What is geology?",
            "What is geography?",
            
            # Study Skills
            "How to study effectively?",
            "How to write research papers?",
            "What is research methodology?",
            
            # General interaction
            "Hello",
            "Hi",
            "Help me",
            "Thank you",
            "How are you?",
            "What can you do?",
            "Tell me about yourself"
        ]
        
        # Adaptive TTL tracking
        self.popularity_scores = {}  # key -> popularity score
        self.access_patterns = {}    # key -> list of access times
        
        # Conversational context tracking
        self.conversation_contexts = {}  # session_id -> conversation context
        self.follow_up_patterns = {
            'clarification': ['explain more', 'i don\'t understand', 'can you clarify', 'what do you mean', 'simpler', 'easier'],
            'examples': ['example', 'examples', 'show me', 'for instance', 'like what'],
            'details': ['more details', 'tell me more', 'elaborate', 'in depth', 'detailed'],
            'different': ['different way', 'another way', 'differently', 'rephrase']
        }
        
        # Short-term memory system
        self.short_term_memory = {}  # session_id -> memory context
        self.memory_size = 10  # Remember last 10 conversations
        self.adaptive_responses = 0  # Track adaptive response count
        
        logger.info("Advanced hybrid cache manager with conversational context initialized")
    
    def _generate_key(self, prefix: str, **kwargs) -> str:
        """Generate cache key from parameters"""
        # Sort keys for consistent hashing
        sorted_params = json.dumps(kwargs, sort_keys=True)
        key_str = f"{prefix}:{sorted_params}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _calculate_adaptive_ttl(self, key: str, base_ttl: int) -> int:
        """Calculate adaptive TTL based on popularity and access patterns"""
        try:
            popularity = self.popularity_scores.get(key, 0)
            access_times = self.access_patterns.get(key, [])
            
            # Base multiplier
            multiplier = 1.0
            
            # Popularity boost (more popular = longer TTL)
            if popularity > 10:
                multiplier *= 2.0  # Very popular
            elif popularity > 5:
                multiplier *= 1.5  # Popular
            elif popularity > 2:
                multiplier *= 1.2  # Somewhat popular
            
            # Recent access pattern boost
            current_time = time.time()
            recent_accesses = [t for t in access_times if current_time - t < 3600]  # Last hour
            
            if len(recent_accesses) > 5:
                multiplier *= 1.5  # Frequently accessed recently
            elif len(recent_accesses) > 2:
                multiplier *= 1.2  # Moderately accessed recently
            
            # Calculate final TTL
            adaptive_ttl = int(base_ttl * multiplier)
            
            # Cap the TTL (min 5 minutes, max 24 hours)
            adaptive_ttl = max(300, min(adaptive_ttl, 86400))
            
            return adaptive_ttl
            
        except Exception as e:
            logger.error("Error calculating adaptive TTL: %s", e)
            return base_ttl
    def _update_access_pattern(self, key: str):
        """Update access patterns for adaptive TTL calculation"""
        try:
            current_time = time.time()
            
            # Update popularity score
            self.popularity_scores[key] = self.popularity_scores.get(key, 0) + 1
            
            # Update access times (keep last 20 accesses)
            if key not in self.access_patterns:
                self.access_patterns[key] = []
            
            self.access_patterns[key].append(current_time)
            
            # Keep only recent access times (last 20)
            if len(self.access_patterns[key]) > 20:
                self.access_patterns[key] = self.access_patterns[key][-20:]
                
        except Exception as e:
            logger.error("Error updating access pattern: %s", e)
    
    def get_chat_response(self, prompt: str, model: str, use_rag: bool = False, 
                         course_code: str = None, session_id: str = None) -> Optional[str]:
        """Get cached chat response with conversational context and short-term memory"""
        logger.info("CACHE GET: prompt='{prompt}', model='{model}', use_rag=%s", use_rag)
        
        # Check for follow-up patterns first
        if session_id and self._is_follow_up_question(prompt, session_id):
            follow_up_response = self._handle_follow_up(prompt, session_id)
            if follow_up_response:
                logger.info("Follow-up response for: %s...", prompt[:50])
                return follow_up_response
        
        # Generate exact key first
        exact_key = self._generate_key(
            'chat',
            prompt=prompt.lower().strip(),
            model=model,
            use_rag=use_rag,
            course_code=course_code
        )
        
        logger.info("Cache key: %s (for prompt: %s)", exact_key, prompt.lower().strip()[:50])
        
        # Update access patterns for adaptive TTL
        self._update_access_pattern(exact_key)
        
        # L1 Cache: DISABLED - Skip memory cache to avoid corruption
        # cached = self.chat_cache.get(exact_key)
        # if cached:
        #     self.l1_hits += 1
        #     logger.info(f"L1 Exact Cache HIT for: {prompt[:50]}...")
        #     return cached
        logger.info("L1 Cache DISABLED - checking L2 database cache only")
        
        # L2 Cache: Check database (persistent) - exact match
        cached = self.db_cache_backend.get(exact_key)
        if cached:
            self.l2_hits += 1
            # Extract structured response if available
            if isinstance(cached, dict) and cached.get('is_structured') and 'structured_response' in cached:
                structured_response = cached['structured_response']
                # L1 Cache DISABLED - Don't store in memory cache
                # self.chat_cache.set(exact_key, structured_response)
                # Add conversational context
                contextual_response = self._add_conversational_context(structured_response, prompt, session_id)
            else:
                # Handle regular cached response
                response_text = cached.get('response', str(cached)) if isinstance(cached, dict) else str(cached)
                # L1 Cache DISABLED - Don't store in memory cache
                # self.chat_cache.set(exact_key, response_text)
                contextual_response = self._add_conversational_context(response_text, prompt, session_id)
            
            # Apply adaptive memory
            adaptive_response = self._apply_adaptive_memory(contextual_response, prompt, session_id)
            
            logger.info("L2 Exact Cache HIT for: %s...", prompt[:50])
            return adaptive_response
        
        # Semantic Cache: Look for similar questions
        semantic_result = self._find_semantic_match(prompt, model, use_rag, course_code)
        if semantic_result:
            self.semantic_hits += 1
            # Calculate adaptive TTL for popular content
            adaptive_ttl = self._calculate_adaptive_ttl(exact_key, 1800)
            # Store under exact key for future exact matches - L1 Cache DISABLED
            # self.chat_cache.set(exact_key, semantic_result)
            self.db_cache_backend.set(exact_key, semantic_result, "chat", ttl=adaptive_ttl)
            # Add conversational context and adaptive response
            contextual_response = self._add_conversational_context(semantic_result, prompt, session_id)
            adaptive_response = self._apply_adaptive_memory(contextual_response, prompt, session_id)
            
            logger.info("Semantic Cache HIT (TTL: %ss) for: %s...", adaptive_ttl, prompt[:50])
            return adaptive_response
        
        # Cache miss
        self.misses += 1
        logger.info("Cache MISS: No cached response found for: %s...", prompt[:50])
        return None
    
    def _find_semantic_match(self, prompt: str, model: str, use_rag: bool = False, 
                           course_code: str = None) -> Optional[str]:
        """Find semantically similar cached responses"""
        try:
            # Get normalized form of the question
            normalized_prompt = self.semantic_similarity.normalize_question(prompt)
            
            # Search database for similar questions
            with self.db_cache_backend.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT cache_data 
                    FROM response_cache 
                    WHERE cache_type = 'chat' 
                    AND expires_at > NOW()
                    ORDER BY hit_count DESC
                    LIMIT 100
                """))
                
                best_match = None
                best_score = 0.0
                similarity_threshold = 0.75  # 75% similarity required
                
                for row in result:
                    cache_data_str = row[0]
                    
                    try:
                        # Parse cache data
                        cache_data = json.loads(cache_data_str)
                        
                        # Handle both old format (string) and new format (dict)
                        if isinstance(cache_data, str):
                            # Old format - skip semantic matching
                            continue
                        elif isinstance(cache_data, dict):
                            # New format with metadata
                            cached_prompt = cache_data.get('original_prompt', '')
                            cached_normalized = cache_data.get('normalized_prompt', '')
                            cached_model = cache_data.get('model', model)
                            cached_use_rag = cache_data.get('use_rag', use_rag)
                            cached_course_code = cache_data.get('course_code', course_code)
                            
                            # Check if context matches (model, rag, course)
                            if (cached_model != model or 
                                cached_use_rag != use_rag or 
                                cached_course_code != course_code):
                                continue
                            
                            # Calculate similarity
                            score = self.semantic_similarity.get_similarity_score(prompt, cached_prompt)
                            
                            # Also check normalized forms
                            if cached_normalized and normalized_prompt:
                                normalized_score = 1.0 if cached_normalized == normalized_prompt else 0.0
                                score = max(score, normalized_score)
                            
                            if score > best_score and score >= similarity_threshold:
                                best_score = score
                                # Return structured response if available, otherwise simple response
                                if cache_data.get('is_structured') and 'structured_response' in cache_data:
                                    best_match = cache_data['structured_response']
                                else:
                                    best_match = cache_data.get('response', cache_data_str)
                                logger.info("Found semantic match (score: %.2f) for: %s... -> %s...", score, prompt[:30], cached_prompt[:30])
                        
                    except (json.JSONDecodeError, KeyError) as e:
                        # Handle old cache format or corrupted data
                        continue
                
                return best_match
                
        except Exception as e:
            logger.error("Error in semantic matching: %s", e)
            return None
    
    def set_chat_response(self, prompt: str, model: str, response: Any,
                         use_rag: bool = False, course_code: str = None, 
                         quality_score: float = 0.5):
        """Cache chat response with adaptive TTL and compression"""
        logger.info("CACHE SET: prompt='{prompt}', model='{model}', use_rag=%s", use_rag)
        
        key = self._generate_key(
            'chat',
            prompt=prompt.lower().strip(),
            model=model,
            use_rag=use_rag,
            course_code=course_code
        )
        
        logger.info("Cache store key: %s (for prompt: %s)", key, prompt.lower().strip()[:50])
        
        # Calculate adaptive TTL
        adaptive_ttl = self._calculate_adaptive_ttl(key, 1800)
        
        # L1 Cache DISABLED - Don't store in memory cache
        # self.chat_cache.set(key, response)
        
        # Store in L2 cache (database) with semantic metadata and adaptive TTL
        self._set_chat_response_with_metadata(key, prompt, response, model, use_rag, course_code, adaptive_ttl, quality_score)
        
        logger.info("Cached chat response (TTL: %ss) for: %s...", adaptive_ttl, prompt[:50])
    def _set_chat_response_with_metadata(self, key: str, prompt: str, response: Any, 
                                        model: str, use_rag: bool, course_code: str, 
                                        ttl: int, quality_score: float):
        """Store chat response with semantic metadata in database"""
        try:
            # Normalize prompt for semantic matching
            normalized_prompt = self.semantic_similarity.normalize_question(prompt)
            
            # Handle structured responses (from cache warming)
            if isinstance(response, dict) and 'primary' in response:
                # This is a structured response from cache warming
                cache_data = {
                    'original_prompt': prompt,
                    'normalized_prompt': normalized_prompt,
                    'model': model,
                    'use_rag': use_rag,
                    'course_code': course_code,
                    'quality_score': quality_score,
                    'is_structured': True,
                    'structured_response': response['primary'],  # Store primary response
                    'full_structured_data': response,  # Store full structured data
                    'timestamp': time.time()
                }
            else:
                # Regular response
                response_text = response.get('response', str(response)) if isinstance(response, dict) else str(response)
                cache_data = {
                    'original_prompt': prompt,
                    'normalized_prompt': normalized_prompt,
                    'response': response_text,
                    'model': model,
                    'use_rag': use_rag,
                    'course_code': course_code,
                    'quality_score': quality_score,
                    'is_structured': False,
                    'timestamp': time.time()
                }
            
            # Store in database with metadata
            self.db_cache_backend.set(key, cache_data, "chat", ttl=ttl)
            
        except Exception as e:
            logger.error("Error storing chat response with metadata: %s", e)
            # Fallback: store simple response
            simple_response = str(response)
            self.db_cache_backend.set(key, simple_response, "chat", ttl=ttl)
    
    def remove_chat_response(self, prompt: str, model: str = "qwen", 
                           use_rag: bool = False, course_code: str = None):
        """Remove cached chat response (for negative feedback)"""
        logger.info("CACHE REMOVE: prompt='{prompt}', model='{model}', use_rag=%s", use_rag)
        
        key = self._generate_key(
            'chat',
            prompt=prompt.lower().strip(),
            model=model,
            use_rag=use_rag,
            course_code=course_code
        )
        
        try:
            # Remove from L1 cache (memory) - currently disabled but for future use
            # self.chat_cache.cache.pop(key, None)
            
            # Remove from L2 cache (database)
            self.db_cache_backend.delete(key)
            
            # Clean up access patterns
            self.access_patterns.pop(key, None)
            self.popularity_scores.pop(key, None)
            
            logger.info("Removed cached response for: %s...", prompt[:50])
            return True
            
        except Exception as e:
            logger.error("Error removing cached response: %s", e)
            return False
    
    def clear_user_cache(self, username: str):
        """Clear any cached data for a specific user (placeholder for future user-specific caching)"""
        try:
            # Currently our cache is not user-specific, but this is a placeholder
            # for future user-specific cache clearing functionality
            logger.info("Cache clear requested for user %s (no user-specific cache currently)", username)
            return True
        except Exception as e:
            logger.error("Error clearing user cache: %s", e)
            return False
    
    # ==================== HYBRID RAG CACHING ====================
    
    def get_rag_results(self, query: str, course_code: str = None, 
                       top_k: int = 5) -> Optional[list]:
        """Get cached RAG search results using hybrid approach"""
        key = self._generate_key(
            'rag',
            query=query.lower().strip(),
            course_code=course_code,
            top_k=top_k
        )
        
        # L1 Cache: Check memory first
        cached = self.rag_cache.get(key)
        if cached:
            self.l1_hits += 1
            logger.info("L1 RAG cache HIT for query: %s...", query[:50])
            return cached
        
        # L2 Cache: Check database
        cached = self.db_cache_backend.get(key)
        if cached:
            self.l2_hits += 1
            # Store in L1 cache for future fast access
            self.rag_cache.set(key, cached)
            logger.info("L2 RAG cache HIT for query: %s...", query[:50])
            return cached
        
        self.misses += 1
        return None
    # set_rag_results removed - unused function
    # invalidate_rag_cache removed - unused function
    
    def get_db_query(self, query_name: str, **params) -> Optional[Any]:
        """Get cached database query result using hybrid approach"""
        key = self._generate_key(f'db_{query_name}', **params)
        
        # L1 Cache: Check memory first
        cached = self.db_cache.get(key)
        if cached:
            self.l1_hits += 1
            return cached
        
        # L2 Cache: Check database
        cached = self.db_cache_backend.get(key)
        if cached:
            self.l2_hits += 1
            # Store in L1 cache for future fast access
            self.db_cache.set(key, cached)
            return cached
        
        self.misses += 1
        return None
    # set_db_query removed - unused function
    # invalidate_db_cache removed - unused function
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics for hybrid system"""
        # Clean expired entries first (method removed - skip this step)
        
        # Get L1 (Memory) stats
        l1_stats = {
            'chat': self.chat_cache.get_stats(),
            'rag': self.rag_cache.get_stats(),
            'db': self.db_cache.get_stats(),
            'total_size': (
                len(self.chat_cache.cache) + 
                len(self.rag_cache.cache) + 
                len(self.db_cache.cache)
            )
        }
        
        # Get L2 (Database) stats
        l2_stats = self.db_cache_backend.get_stats()
        
        # Calculate hit rates
        total_requests = self.l1_hits + self.l2_hits + self.semantic_hits + self.misses
        l1_hit_rate = (self.l1_hits / total_requests * 100) if total_requests > 0 else 0
        l2_hit_rate = (self.l2_hits / total_requests * 100) if total_requests > 0 else 0
        semantic_hit_rate = (self.semantic_hits / total_requests * 100) if total_requests > 0 else 0
        overall_hit_rate = ((self.l1_hits + self.l2_hits + self.semantic_hits) / total_requests * 100) if total_requests > 0 else 0
        
        # Get warming stats
        warm_stats = self.get_warm_stats()
        
        # Calculate advanced metrics
        avg_popularity = sum(self.popularity_scores.values()) / len(self.popularity_scores) if self.popularity_scores else 0
        top_popular_keys = sorted(self.popularity_scores.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'hybrid_stats': {
                'l1_hits': self.l1_hits,
                'l2_hits': self.l2_hits,
                'semantic_hits': self.semantic_hits,
                'warm_hits': self.warm_hits,
                'misses': self.misses,
                'total_requests': total_requests,
                'l1_hit_rate': round(l1_hit_rate, 2),
                'l2_hit_rate': round(l2_hit_rate, 2),
                'semantic_hit_rate': round(semantic_hit_rate, 2),
                'overall_hit_rate': round(overall_hit_rate, 2)
            },
            'l1_cache': l1_stats,
            'l2_cache': l2_stats,
            'cache_efficiency': {
                'memory_vs_db_ratio': f"{self.l1_hits}:{self.l2_hits}" if self.l2_hits > 0 else f"{self.l1_hits}:0",
                'semantic_benefit': self.semantic_hits > 0,
                'persistence_benefit': self.l2_hits > 0,
                'smart_matching': f"{self.semantic_hits} questions answered via similarity",
                'cache_warming': warm_stats
            },
            'advanced_metrics': {
                'avg_popularity_score': round(avg_popularity, 2),
                'tracked_patterns': len(self.access_patterns),
                'top_popular_content': [{'key': k[:16] + '...', 'score': v} for k, v in top_popular_keys],
                'adaptive_ttl_enabled': True,
                'compression_enabled': True,
                'ml_similarity_enabled': True,
                'short_term_memory_enabled': True,
                'adaptive_responses_generated': self.adaptive_responses
            },
            'memory_system': self.get_memory_stats()
        }
    
    def clear_all(self):
        """Clear all caches (L1 and L2)"""
        # Clear L1 (Memory)
        self.chat_cache.clear()
        self.rag_cache.clear()
        self.db_cache.clear()
        
        # Clear L2 (Database)
        try:
            with self.db_cache_backend.engine.connect() as conn:
                conn.execute(text("DELETE FROM {}".format(self.db_cache_backend.table_name)))
                conn.commit()
        except Exception as e:
            logger.warning("Could not clear L2 database cache: %s", e)
        
        # Reset stats
        self.l1_hits = 0
        self.l2_hits = 0
        self.semantic_hits = 0
        self.warm_hits = 0
        self.misses = 0
        
        # Clear adaptive TTL data
        self.popularity_scores.clear()
        self.access_patterns.clear()
        
        # Clear short-term memory
        self.short_term_memory.clear()
        self.adaptive_responses = 0
        
        logger.info("[CACHE] All hybrid caches cleared (Memory + Database)")
    # maintenance removed - unused function
    # warm_cache removed - unused function
    
    def _generate_warm_response(self, question: str) -> Dict[str, Any]:
        """Generate multi-level responses for cache warming"""
        # This creates a structured response with multiple explanation levels
        # In production, you'd integrate with your actual PHI-2 service
        
        warm_responses = {
            # Technology & Computer Science
            "what is artificial intelligence": {
                "primary": "Artificial Intelligence (AI) is a branch of computer science that aims to create intelligent machines capable of performing tasks that typically require human intelligence, such as learning, reasoning, problem-solving, and understanding natural language.",
                "simple": "AI is like making computers smart enough to think and solve problems like humans do. Think of it as teaching machines to be clever!",
                "detailed": "Artificial Intelligence encompasses machine learning, natural language processing, computer vision, robotics, and expert systems. It involves algorithms that can process data, recognize patterns, make decisions, and adapt to new situations without explicit programming for each scenario.",
                "examples": "Examples of AI include: voice assistants like Siri, recommendation systems on Netflix, self-driving cars, chess-playing computers, and chatbots like me!",
                "follow_ups": ["Would you like to know about different types of AI?", "Are you interested in how AI learns from data?", "Would you like some real-world examples of AI?"]
            },
            "what is computer science": {
                "primary": "Computer Science is the study of computational systems, algorithms, and the design of computer systems and their applications. It combines mathematical rigor with engineering pragmatism.",
                "simple": "Computer Science is about learning how computers work and how to make them solve problems. It's like being a digital problem-solver!",
                "detailed": "CS covers programming, algorithms, data structures, software engineering, computer systems, databases, artificial intelligence, human-computer interaction, and theoretical computer science.",
                "examples": "CS graduates work as software developers, data scientists, cybersecurity experts, game developers, and AI researchers at companies like Google, Microsoft, and startups.",
                "follow_ups": ["Want to know about CS career paths?", "Interested in programming languages?", "Curious about CS specializations?"]
            },
            
            # Mathematics & Statistics
            "what is mathematics": {
                "primary": "Mathematics is the abstract science of number, quantity, and space, either as abstract concepts (pure mathematics) or as applied to other disciplines (applied mathematics).",
                "simple": "Math is the language of patterns, numbers, and logical thinking. It helps us understand and describe the world around us!",
                "detailed": "Mathematics includes algebra, calculus, geometry, statistics, discrete mathematics, and mathematical analysis. It provides tools for problem-solving in science, engineering, economics, and technology.",
                "examples": "Math is used in cryptography for internet security, in algorithms for search engines, in statistics for medical research, and in calculus for physics and engineering.",
                "follow_ups": ["Want to know about different branches of math?", "Interested in math applications?", "Curious about math careers?"]
            },
            "what is statistics": {
                "primary": "Statistics is the discipline that concerns the collection, organization, analysis, interpretation, and presentation of data.",
                "simple": "Statistics is about collecting information (data) and figuring out what it means. It's like being a data detective!",
                "detailed": "Statistics includes descriptive statistics (summarizing data), inferential statistics (making predictions), probability theory, hypothesis testing, and regression analysis.",
                "examples": "Statistics is used in medical trials to test new drugs, in polling to predict elections, in quality control in manufacturing, and in A/B testing for websites.",
                "follow_ups": ["Want to learn about probability?", "Interested in data analysis?", "Curious about statistical software?"]
            },
            
            # Natural Sciences
            "what is physics": {
                "primary": "Physics is the natural science that studies matter, its motion and behavior through space and time, and the related entities of energy and force.",
                "simple": "Physics is about understanding how things move, why they move, and what makes up everything around us - from tiny atoms to huge stars!",
                "detailed": "Physics includes mechanics, thermodynamics, electromagnetism, optics, quantum mechanics, and relativity. It seeks to understand the fundamental laws governing the universe.",
                "examples": "Physics principles enable GPS navigation, MRI machines, solar panels, lasers, and help us understand black holes and quantum computers.",
                "follow_ups": ["Want to know about quantum physics?", "Interested in physics careers?", "Curious about physics experiments?"]
            },
            "what is chemistry": {
                "primary": "Chemistry is the scientific discipline involved with elements and compounds composed of atoms, molecules and ions: their composition, structure, properties, behavior and the changes they undergo.",
                "simple": "Chemistry is like cooking with atoms! It's about mixing different elements to create new substances and understanding how they react.",
                "detailed": "Chemistry includes organic chemistry (carbon-based compounds), inorganic chemistry (minerals and metals), physical chemistry (chemical physics), and biochemistry (chemistry in living systems).",
                "examples": "Chemistry creates medicines, plastics, fertilizers, batteries, and helps develop new materials like graphene and superconductors.",
                "follow_ups": ["Want to learn about organic chemistry?", "Interested in chemical reactions?", "Curious about chemistry careers?"]
            },
            "what is biology": {
                "primary": "Biology is the natural science that studies life and living organisms, including their physical structure, chemical processes, molecular interactions, physiological mechanisms, development and evolution.",
                "simple": "Biology is the study of all living things - from tiny bacteria to huge whales, and everything that makes them alive and growing!",
                "detailed": "Biology encompasses molecular biology, genetics, ecology, evolution, physiology, anatomy, and biotechnology. It seeks to understand life at all levels from molecules to ecosystems.",
                "examples": "Biology helps develop vaccines, understand diseases, protect endangered species, improve crops, and advance personalized medicine.",
                "follow_ups": ["Want to know about genetics?", "Interested in ecology?", "Curious about biotechnology?"]
            },
            
            # Engineering
            "what is engineering": {
                "primary": "Engineering is the use of scientific principles to design and build machines, structures, and other items, including bridges, tunnels, roads, vehicles, and buildings.",
                "simple": "Engineering is about solving real-world problems by building things that help people. Engineers are like professional problem-solvers!",
                "detailed": "Engineering includes mechanical, electrical, civil, chemical, aerospace, biomedical, and software engineering. It applies math and science to create practical solutions.",
                "examples": "Engineers design smartphones, build bridges, develop medical devices, create renewable energy systems, and design spacecraft.",
                "follow_ups": ["Want to know about engineering specializations?", "Interested in engineering projects?", "Curious about engineering careers?"]
            },
            
            # Business & Economics
            "what is business": {
                "primary": "Business is the activity of making one's living or making money by producing or buying and selling products or services.",
                "simple": "Business is about creating value for people by providing products or services they need, while making money to keep the business running.",
                "detailed": "Business studies include management, marketing, finance, accounting, operations, strategy, entrepreneurship, and business ethics. It covers how organizations operate and compete.",
                "examples": "Business concepts apply to startups, corporations, non-profits, and even personal finance. Think Amazon, local restaurants, or charity organizations.",
                "follow_ups": ["Want to learn about entrepreneurship?", "Interested in marketing?", "Curious about business careers?"]
            },
            "what is economics": {
                "primary": "Economics is the social science that studies the production, distribution, and consumption of goods and services.",
                "simple": "Economics is about understanding how people make choices about money, resources, and what to buy or sell.",
                "detailed": "Economics includes microeconomics (individual and firm behavior), macroeconomics (national and global economies), and specialized fields like behavioral economics and econometrics.",
                "examples": "Economics explains inflation, unemployment, stock markets, trade policies, and helps governments make decisions about taxes and spending.",
                "follow_ups": ["Want to learn about supply and demand?", "Interested in global economics?", "Curious about economic careers?"]
            },
            
            # Social Sciences
            "what is psychology": {
                "primary": "Psychology is the scientific study of the mind and behavior. It encompasses the biological influences, social pressures, and environmental factors that affect how people think, act, and feel.",
                "simple": "Psychology is about understanding why people think, feel, and behave the way they do. It's like being a detective of the human mind!",
                "detailed": "Psychology includes cognitive psychology, social psychology, developmental psychology, clinical psychology, and neuropsychology. It uses scientific methods to study mental processes.",
                "examples": "Psychology helps treat mental health disorders, improve education methods, design better user interfaces, and understand group behavior in organizations.",
                "follow_ups": ["Want to know about different psychology fields?", "Interested in mental health?", "Curious about psychology careers?"]
            },
            
            # Health & Medical Sciences
            "what is medicine": {
                "primary": "Medicine is the science and practice of caring for a patient, managing the diagnosis, prognosis, prevention, treatment, palliation of their injury or disease, and promoting their health.",
                "simple": "Medicine is about helping sick people get better and keeping healthy people from getting sick. Doctors are like health detectives and fixers!",
                "detailed": "Medicine includes anatomy, physiology, pathology, pharmacology, surgery, internal medicine, pediatrics, and many specialized fields like cardiology and neurology.",
                "examples": "Medical advances include vaccines, antibiotics, surgical techniques, medical imaging (X-rays, MRI), and personalized treatments based on genetics.",
                "follow_ups": ["Want to know about medical specialties?", "Interested in medical research?", "Curious about healthcare careers?"]
            },
            
            # Arts & Design
            "what is fine arts": {
                "primary": "Fine arts are creative art forms, primarily visual arts whose products are to be appreciated primarily or solely for their imaginative, aesthetic, or intellectual content.",
                "simple": "Fine arts is about creating beautiful things that make people think and feel - like paintings, sculptures, and drawings!",
                "detailed": "Fine arts include painting, sculpture, drawing, printmaking, photography, and mixed media. It emphasizes creative expression, aesthetic beauty, and conceptual depth.",
                "examples": "Famous fine art includes the Mona Lisa, Michelangelo's David, Van Gogh's Starry Night, and contemporary installations in modern art museums.",
                "follow_ups": ["Want to know about art techniques?", "Interested in art history?", "Curious about art careers?"]
            },
            
            # General Interaction
            "hello": {
                "primary": "Hello! I'm FAIA, your AI assistant. How can I help you today?",
                "simple": "Hi! I'm here to help you learn. What would you like to know?",
                "detailed": "Welcome! I'm FAIA (Focused Academic Information Assistant), designed to help students with AI, programming, and academic topics. I can explain concepts, provide examples, and guide your learning journey.",
                "examples": "I can help with questions like 'What is AI?', 'How do I learn programming?', or 'Explain algorithms simply'.",
                "follow_ups": ["What topic would you like to explore?", "Are you new to AI and programming?", "Do you have a specific assignment or project?"]
            }
        }
        
        question_lower = question.lower().strip()
        if question_lower in warm_responses:
            return warm_responses[question_lower]
        else:
            return {
                "primary": f"I'd be happy to help you with '{question}'. This is a cached response for demonstration.",
                "simple": f"Let me help you understand '{question}' in simple terms.",
                "detailed": f"Here's a detailed explanation of '{question}' with more context and examples.",
                "examples": f"Here are some practical examples related to '{question}'.",
                "follow_ups": [
                    "Would you like me to explain this differently?",
                    "Do you have any specific questions about this topic?",
                    "Would you like to see some examples?"
                ]
            }
    
    def get_warm_stats(self) -> Dict[str, Any]:
        """Get cache warming statistics"""
        return {
            "warm_hits": self.warm_hits,
            "common_questions_count": len(self.common_questions),
            "warmed_percentage": (self.warm_hits / len(self.common_questions) * 100) if self.common_questions else 0
        }
    
    # ==================== CONVERSATIONAL CONTEXT ====================
    # _update_conversation_context removed - unused function
    
    def _is_follow_up_question(self, prompt: str, session_id: str) -> bool:
        """Detect if this is a follow-up question"""
        if session_id not in self.conversation_contexts:
            return False
        
        context = self.conversation_contexts[session_id]
        if not context['history']:
            return False
        
        prompt_lower = prompt.lower()
        
        # Check for follow-up patterns
        for pattern_type, patterns in self.follow_up_patterns.items():
            if any(pattern in prompt_lower for pattern in patterns):
                return True
        
        # Check for pronouns indicating reference to previous topic
        pronouns = ['it', 'this', 'that', 'they', 'them']
        if any(pronoun in prompt_lower.split() for pronoun in pronouns):
            return True
        
        return False
    
    def _handle_follow_up(self, prompt: str, session_id: str) -> Optional[str]:
        """Handle follow-up questions with context-aware responses"""
        if session_id not in self.conversation_contexts:
            return None
        
        context = self.conversation_contexts[session_id]
        if not context['history']:
            return None
        
        prompt_lower = prompt.lower()
        
        # Determine follow-up type
        follow_up_type = None
        for pattern_type, patterns in self.follow_up_patterns.items():
            if any(pattern in prompt_lower for pattern in patterns):
                follow_up_type = pattern_type
                break
        
        if not follow_up_type:
            return None
        
        # Get the last response data if available
        last_response_data = context.get('last_response_data')
        if not last_response_data or not isinstance(last_response_data, dict):
            return None
        
        # Generate appropriate follow-up response
        context['follow_up_count'] += 1
        
        if follow_up_type == 'clarification':
            context['last_response_type'] = 'simple'
            return last_response_data.get('simple', last_response_data.get('primary'))
        elif follow_up_type == 'examples':
            context['last_response_type'] = 'examples'
            return last_response_data.get('examples', "Let me provide some examples related to this topic.")
        elif follow_up_type == 'details':
            context['last_response_type'] = 'detailed'
            return last_response_data.get('detailed', last_response_data.get('primary'))
        elif follow_up_type == 'different':
            # Alternate between simple and detailed
            if context.get('last_response_type') == 'simple':
                context['last_response_type'] = 'detailed'
                return last_response_data.get('detailed', last_response_data.get('primary'))
            else:
                context['last_response_type'] = 'simple'
                return last_response_data.get('simple', last_response_data.get('primary'))
        
        return None
    
    def _add_conversational_context(self, cached_response: Any, prompt: str, session_id: str) -> str:
        """Add conversational context to cached responses"""
        if not session_id:
            # No session context, return as-is
            if isinstance(cached_response, dict):
                return cached_response.get('response', str(cached_response))
            return str(cached_response)
        
        # Handle structured responses (from cache warming)
        if isinstance(cached_response, dict):
            if 'primary' in cached_response:
                # This is a structured response from cache warming
                context = self.conversation_contexts.get(session_id, {})
                context['last_response_data'] = cached_response
                context['last_topic'] = self._extract_topic(prompt)
                context['last_response_type'] = 'primary'
                
                # Add follow-up suggestions
                response = cached_response['primary']
                if 'follow_ups' in cached_response and cached_response['follow_ups']:
                    follow_up = cached_response['follow_ups'][0]  # Use first follow-up
                    response += f"\n\n{follow_up}"
                
                return response
            elif 'response' in cached_response:
                # This is a regular cached response with metadata
                return cached_response['response']
            else:
                return str(cached_response)
        
        # Regular string response
        return str(cached_response)
    
    def _extract_topic(self, prompt: str) -> str:
        """Extract main topic from prompt for context tracking"""
        prompt_lower = prompt.lower()
        
        # Define topic keywords
        topics = {
            'ai': ['ai', 'artificial intelligence'],
            'ml': ['machine learning', 'ml'],
            'programming': ['programming', 'coding', 'code'],
            'algorithm': ['algorithm', 'algorithms'],
            'data': ['data structure', 'data structures']
        }
        
        for topic, keywords in topics.items():
            if any(keyword in prompt_lower for keyword in keywords):
                return topic
        
        return 'general'
    
    # ==================== SHORT-TERM MEMORY SYSTEM ====================
    # _initialize_memory removed - unused function
    # _add_to_memory removed - unused function
    
    def _classify_question_type(self, question: str) -> str:
        """Classify the type of question being asked"""
        question_lower = question.lower()
        
        # Question type patterns
        if any(word in question_lower for word in ['what is', 'define', 'meaning']):
            return 'definition'
        elif any(word in question_lower for word in ['how to', 'how do', 'how can']):
            return 'how_to'
        elif any(word in question_lower for word in ['why', 'reason', 'because']):
            return 'explanation'
        elif any(word in question_lower for word in ['example', 'instance', 'show me']):
            return 'example_request'
        elif any(word in question_lower for word in ['compare', 'difference', 'vs', 'versus']):
            return 'comparison'
        elif any(word in question_lower for word in ['hello', 'hi', 'hey']):
            return 'greeting'
        elif any(word in question_lower for word in ['thank', 'thanks']):
            return 'gratitude'
        else:
            return 'general'
    
    def _infer_satisfaction(self, current_question: str, conversation_history: List[Dict]) -> str:
        """Infer user satisfaction from question patterns"""
        if not conversation_history:
            return 'neutral'
        
        current_lower = current_question.lower()
        
        # Signs of confusion/dissatisfaction
        confusion_indicators = [
            'i don\'t understand', 'confused', 'unclear', 'what do you mean',
            'can you clarify', 'i\'m lost', 'doesn\'t make sense'
        ]
        
        # Signs of satisfaction/understanding
        satisfaction_indicators = [
            'thank you', 'thanks', 'got it', 'understand now', 'clear now',
            'that helps', 'makes sense', 'i see'
        ]
        
        # Signs of wanting more information
        curiosity_indicators = [
            'tell me more', 'what else', 'more details', 'elaborate',
            'interesting', 'can you expand'
        ]
        
        if any(indicator in current_lower for indicator in confusion_indicators):
            return 'confused'
        elif any(indicator in current_lower for indicator in satisfaction_indicators):
            return 'satisfied'
        elif any(indicator in current_lower for indicator in curiosity_indicators):
            return 'curious'
        else:
            return 'neutral'
    # _update_user_preferences removed - unused function
    
    def _get_adaptive_response_context(self, session_id: str, current_question: str) -> Dict[str, Any]:
        """Generate adaptive response context based on memory"""
        if session_id not in self.short_term_memory:
            return {}
        
        memory = self.short_term_memory[session_id]
        preferences = memory['user_preferences']
        conversations = memory['conversations']
        
        # Analyze conversation patterns
        context = {
            'user_preferences': preferences,
            'conversation_patterns': {
                'recent_topics': [conv['topic'] for conv in conversations[-3:]],
                'question_types': [conv['question_type'] for conv in conversations[-5:]],
                'satisfaction_levels': [conv['satisfaction_inferred'] for conv in conversations[-3:]],
                'response_types_used': [conv['response_type'] for conv in conversations[-5:]]
            },
            'session_insights': {
                'is_struggling': 'confused' in [conv['satisfaction_inferred'] for conv in conversations[-3:]],
                'is_engaged': len(set(conv['topic'] for conv in conversations)) > 2,
                'prefers_examples': preferences['preferred_explanation_style'] == 'examples',
                'needs_simpler_explanations': preferences['difficulty_level'] == 'beginner'
            },
            'contextual_references': self._find_contextual_references(conversations, current_question)
        }
        
        return context
    
    def _find_contextual_references(self, conversations: List[Dict], current_question: str) -> List[str]:
        """Find references to previous conversations in current question"""
        references = []
        current_lower = current_question.lower()
        
        # Pronouns and references
        reference_patterns = [
            'that', 'this', 'it', 'they', 'them', 'those', 'these',
            'the previous', 'earlier', 'before', 'you mentioned', 'you said'
        ]
        
        if any(pattern in current_lower for pattern in reference_patterns):
            # Find most relevant previous conversation
            if conversations:
                last_conv = conversations[-1]
                references.append(f"Referring to previous discussion about {last_conv['topic']}")
        
        return references
    
    def _generate_adaptive_response_prefix(self, context: Dict, current_question: str) -> str:
        """Generate adaptive response prefix based on context"""
        insights = context.get('session_insights', {})
        patterns = context.get('conversation_patterns', {})
        preferences = context.get('user_preferences', {})
        
        prefixes = []
        
        # Handle struggling users
        if insights.get('is_struggling'):
            prefixes.append("Let me try to explain this more clearly.")
        
        # Handle engaged users
        elif insights.get('is_engaged'):
            prefixes.append("Great question! Building on what we discussed,")
        
        # Handle preference-based responses
        elif preferences.get('preferred_explanation_style') == 'examples':
            prefixes.append("Here's a practical example:")
        elif preferences.get('difficulty_level') == 'beginner':
            prefixes.append("Let me break this down simply:")
        elif preferences.get('difficulty_level') == 'advanced':
            prefixes.append("Here's a more detailed explanation:")
        
        # Handle contextual references
        references = context.get('contextual_references', [])
        if references:
            prefixes.append("Connecting to our earlier discussion,")
        
        # Handle topic continuity
        recent_topics = patterns.get('recent_topics', [])
        current_topic = self._extract_topic(current_question)
        if recent_topics and current_topic in recent_topics:
            prefixes.append("Continuing with this topic,")
        
        return prefixes[0] if prefixes else ""
    
    def _should_use_adaptive_response(self, session_id: str) -> bool:
        """Determine if adaptive response should be used"""
        if session_id not in self.short_term_memory:
            return False
        
        memory = self.short_term_memory[session_id]
        conversations = memory['conversations']
        
        # Use adaptive responses if:
        # 1. User has asked multiple questions (engaged)
        # 2. User has shown confusion
        # 3. User has established preferences
        # 4. There are contextual references
        
        return (
            len(conversations) >= 2 and  # At least 2 previous conversations
            (
                any(conv['satisfaction_inferred'] == 'confused' for conv in conversations[-3:]) or
                len(set(conv['topic'] for conv in conversations)) > 1 or
                memory['user_preferences']['preferred_explanation_style'] is not None
            )
        )
    
    def _apply_adaptive_memory(self, base_response: str, current_question: str, session_id: str) -> str:
        """Apply short-term memory to create adaptive responses"""
        if not session_id or not self._should_use_adaptive_response(session_id):
            return base_response
        
        # Get adaptive context
        context = self._get_adaptive_response_context(session_id, current_question)
        
        # Generate adaptive prefix
        adaptive_prefix = self._generate_adaptive_response_prefix(context, current_question)
        
        # Apply adaptations
        adapted_response = base_response
        
        if adaptive_prefix:
            adapted_response = f"{adaptive_prefix} {base_response}"
            self.adaptive_responses += 1
        
        # Add personalized elements based on memory
        insights = context.get('session_insights', {})
        preferences = context.get('user_preferences', {})
        
        # Add difficulty-appropriate suffix
        if insights.get('needs_simpler_explanations'):
            adapted_response += "\n\nWould you like me to explain any part of this more simply?"
        elif preferences.get('difficulty_level') == 'advanced':
            adapted_response += "\n\nWould you like me to go deeper into the technical details?"
        
        # Add topic-specific follow-ups based on interests
        topics_of_interest = preferences.get('topics_of_interest', set())
        current_topic = self._extract_topic(current_question)
        
        if len(topics_of_interest) > 1 and current_topic in topics_of_interest:
            related_topics = topics_of_interest - {current_topic}
            if related_topics:
                related_topic = list(related_topics)[0]
                adapted_response += f"\n\nSince you're also interested in {related_topic}, would you like to know how they connect?"
        
        return adapted_response
    
    def get_memory_stats(self, session_id: str = None) -> Dict[str, Any]:
        """Get short-term memory statistics"""
        if session_id and session_id in self.short_term_memory:
            memory = self.short_term_memory[session_id]
            return {
                'session_id': session_id,
                'conversations_remembered': len(memory['conversations']),
                'user_preferences': memory['user_preferences'],
                'session_stats': memory['session_stats'],
                'memory_insights': {
                    'topics_explored': list(memory['session_stats']['topics_explored']),
                    'session_duration_minutes': (time.time() - memory['session_stats']['session_start']) / 60,
                    'avg_questions_per_minute': memory['session_stats']['total_questions'] / max(1, (time.time() - memory['session_stats']['session_start']) / 60)
                }
            }
        else:
            # Global memory stats
            total_sessions = len(self.short_term_memory)
            total_conversations = sum(len(memory['conversations']) for memory in self.short_term_memory.values())
            
            return {
                'total_active_sessions': total_sessions,
                'total_conversations_remembered': total_conversations,
                'adaptive_responses_generated': self.adaptive_responses,
                'memory_utilization': f"{total_conversations}/{total_sessions * self.memory_size}" if total_sessions > 0 else "0/0"
            }
    # cache_response removed - unused function

# Global cache manager instance
cache_manager = ResponseCacheManager()