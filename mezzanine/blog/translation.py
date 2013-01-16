
from mezzanine.blog.models import BlogPost, BlogCategory

from modeltranslation.translator import translator


translator.register((BlogPost, BlogCategory))
