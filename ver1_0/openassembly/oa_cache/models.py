from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.template.loader import render_to_string
from django.shortcuts import render_to_response
from django.core.cache import cache as memcache
from pirate_ranking.models import get_ranked_list
from pirate_comments.models import get_comments
from pirate_deliberation.models import get_argument_list
from pirate_topics.models import get_topics, get_users
from pirate_forum.models import get_children
from django.contrib import admin
from django.core.context_processors import csrf

from settings import DOMAIN

from pirate_core.middleware import TYPE_KEY, OBJ_KEY, CTYPE_KEY, PHASE_KEY, SEARCH_KEY, S_KEY, STR_KEY
from pirate_core.middleware import START_KEY, END_KEY, DIM_KEY, SCROLL_KEY, RETURN_KEY, SIMPLEBOX_KEY
from pirate_forum.models import get_pretty_url, reverse_pretty_url

from settings import DOMAIN


DIMS = {TYPE_KEY: 'TYPE_KEY', OBJ_KEY: "OBJ_KEY", START_KEY: "START_KEY", STR_KEY: "STR_KEY",
            END_KEY: "END_KEY", DIM_KEY: "DIM_KEY", S_KEY: "S_KEY",
            SCROLL_KEY: "SCROLL_KEY", SEARCH_KEY: "SEARCH_KEY", CTYPE_KEY: "CTYPE_KEY", PHASE_KEY: "PHASE_KEY"}

OPP_DIMS = {'TYPE_KEY': TYPE_KEY, "OBJ_KEY": OBJ_KEY, "START_KEY": START_KEY, "STR_KEY": STR_KEY,
            "END_KEY": END_KEY, "DIM_KEY": DIM_KEY, "S_KEY": S_KEY,
            "SCROLL_KEY": SCROLL_KEY, "SEARCH_KEY": SEARCH_KEY, "CTYPE_KEY": CTYPE_KEY,  "PHASE_KEY": PHASE_KEY}


def initiate_update(obj_pk, content_pk):
    """
    This method is designed to allow objects to access the oa_cache and update their rendered memcache file.
    If these objects
"""
    #update the listing.html
    m = ModelCache.objects.get(html="listing.html")
    #update the detail_dyn.html
    m = ModelCache.objects.get(html="detail_dyn.html")


def interpret_hash(h):
    h = h.replace(DOMAIN, '')[1:]
    l = h.split('/')
    retdict = {}
    if len(l) >= 2:
        rendertype = l[1]
        #rendertype = rendertype[1:]
        key = str(rendertype)
        num_fields = len(l[2:])
        itr = 1
        for dim in l[2:]:
            #if this is the last field, check for hashes and remove them
            if itr == num_fields:
                try:
                    idx = dim.index('#')
                    val = dim[2:idx]
                except:
                    val = dim[2:]
            else:
                val = dim[2:]
            int_key = key + '/' + dim[0:2] + val
            int_key = DIMS[dim[0:2]]
            if int_key == 'STR_KEY':
                ctype_pk, obj_pk = reverse_pretty_url(val)
                retdict['OBJ_KEY'] = obj_pk
                retdict['TYPE_KEY'] = ctype_pk
            else:
                retdict[int_key] = val
    else:
        rendertype = ''
        retdict = {}
    return h, rendertype, retdict


def build_hash(rendertype, paramdict, add_domain=True):
    l = '/p/' + rendertype
    obj_pk = None
    for k, v in paramdict.items():
        if k == 'OBJ_KEY':
            obj_pk = v
        elif k == 'TYPE_KEY':
            ctype_pk = v
        else:
            l += '/' + OPP_DIMS[k] + v
    if obj_pk != None:
        try:
            obj_str = get_pretty_url(ctype_pk, obj_pk)
            l += '/' + OPP_DIMS['STR_KEY'] + obj_str
        except:
            l += '/' + OPP_DIMS['OBJ_KEY'] + obj_pk
            l += '/' + OPP_DIMS['TYPE_KEY'] + ctype_pk
    if add_domain:
        l = DOMAIN + l
    return l


class ModelCache(models.Model):
    """Stores references to cached objects with template
that will be inserted at div_id. content_type
references if this Model is a listing type for lists if
it is a ListCache, or a detailed content item/user if otherwise.
"""
    template = models.CharField(max_length=200)
    div_id = models.CharField(max_length=200)
    content_type = models.CharField(max_length=200)
    main = models.BooleanField(default=False)
    is_recursive = models.BooleanField(default=False)
    jquery_cmd = models.CharField(max_length=200, blank=True, null=True)
    object_specific = models.BooleanField(default=False)

    def recursive_render(self, tree, context, forcerender):
        ret_html = ""
        for obj in tree:
            if isinstance(obj, list):
                context['object'] = obj[0]
                if context['object'] is not None:
                    #context['count'] = len(tree[1])
                    key = str(self.template) + '-' + str(context['object'].pk)
                    val = memcache.get(key)
                    if val is None or forcerender == True or forcerender == context['object'].pk:
                        val = render_to_string(self.template, context)
                    ret_html += '<ul id="' + self.template.replace('.html', '') + str(context['object'].pk) + '" class="' + self.template.replace('.html', '') + '">' + val
                    if len(obj) > 1:
                        ret_html += self.recursive_render(obj[1], context, forcerender) + "</ul></ul>"
                    else:
                        ret_html += '</ul>'
            else:
                context['object'] = obj
                context['count'] = 0
                if context['object'] is not None:
                    key = str(self.template) + '-' + str(context['object'].pk)
                    val = memcache.get(key)
                    if val is None or forcerender == True or forcerender == context['object'].pk:
                        val = render_to_string(self.template, context)
                    ret_html += '<ul id="' + self.template.replace('.html', '') + str(obj.pk) + '" class="' + self.template.replace('.html', '') + '">' + val + "</ul>"
        return ret_html

    def render(self, context, forcerender=True):
        #gets from cache or renders an atomic object given template
        if self.is_recursive == False:
            try:
                key = str(self.template) + '-' + str(context['object'].pk)
            except:
                key = str(self.template) + '-anon'
            obj = memcache.get(key)
            if obj is None or forcerender:
                obj = render_to_string(self.template, context)
                #obj = render_to_string(self.template, context)
                memcache.set(key, obj)
        else:
            obj = self.recursive_render([context['object']], context, forcerender)
        return obj

    def __unicode__(self):
        return '%s %s %s' % (self.template, self.id, self.content_type)


class ListCache(models.Model):
    model_cache = models.CharField(max_length=100, null=True, blank=True)
    template = models.CharField(max_length=200)
    div_id = models.CharField(max_length=200)
    content_type = models.CharField(max_length=200)
    default = models.BooleanField(default=False)

    def get_or_create_list(self, key, paramdict, forcerender=True):
        #returns list of rendered objs
        cache = memcache.get(key)
        if cache is not None and not forcerender:
            cached_list = cache[0]
            tot_items = cache[1]
        elif cache is None or forcerender:
            if paramdict == {}:
                key, rtype, paramdict = interpret_hash(key)
            ctype_id = paramdict.get('TYPE_KEY', None)
            obj_id = paramdict.get('OBJ_KEY', None)
            start = paramdict.get('START_KEY', None)
            end = paramdict.get('END_KEY', None)
            dimension = paramdict.get('DIM_KEY', None)
            ctype_list = paramdict.get('CTYPE_KEY', None)
            phasekey = paramdict.get('PHASE_KEY', None)

            if ctype_id is not None and obj_id is not None:
                content_type = ContentType.objects.get(pk=ctype_id)
                parent = content_type.get_object_for_this_type(pk=obj_id)
            else:
                parent = None

            if start is None or end is None:
                paramdict['START_KEY'] = 0
                paramdict['END_KEY'] = 10

            if dimension is None:
                dimension = 'h'
                paramdict['DIM_KEY'] = 'hn'

            #later these functions can be rendered via some loosely coupled method
            if self.template == 'issues':
                func = get_ranked_list
                update = True
            elif self.template == 'comments':
                func = get_comments
                update = False
            elif self.template == 'yea':
                func = get_argument_list
                dimension = "yea"
                update = False
            elif self.template == 'nay':
                func = get_argument_list
                dimension = "nay"
                update = False
            elif self.template == 'children':
                func = get_ranked_list
                update = False
            elif self.template == 'topics':
                func = get_topics
                update = True
            elif self.template == 'users':
                func = get_users
                update = True
            else:
                func = get_ranked_list
                update = False
            #TODO
            #elif self.template == 'users':
            #    func = get_topics
            #    update = True

            kwr = {'parent': parent, 'start': paramdict['START_KEY'],
                                'end': paramdict['END_KEY'], 'dimension': dimension, 'ctype_list': ctype_list}
            if phasekey is not None:
                kwr['phase'] = phasekey
            cached_list, tot_items = func(**kwr)
            if update:
                codes = memcache.get("rank_update_codes")
                #stores all the encoded pages for tasks/update_ranks
                newkey, rendertype, paramdict = interpret_hash(key)
                if codes is not None:
                    codes[key] = paramdict
                    memcache.set("rank_update_codes", codes)
                else:
                    codes = {}
                    memcache.set("rank_update_codes", codes)
                #save newly rendered list
            memcache.set(key, (cached_list, tot_items))
        return cached_list, tot_items

    def __unicode__(self):
        return '%s %s %s' % (self.template, self.div_id, self.content_type)


class UserSaltCache(models.Model):
    """User salt renders based on object and user,
only rendered when the corresponding model_cache is rendered"""
    model_cache = models.CharField('Object_ID', max_length=100, blank=True, null=True)
    template = models.CharField(max_length=200)
    div_id = models.CharField(max_length=200)
    jquery_cmd = models.CharField(max_length=200)
    is_recursive = models.BooleanField(default=False)
    #if this is a toggled DIV, when re-rendered we want to toggle again
    is_toggle = models.BooleanField(default=False)
    #is this object DIV specific or required an object pk appended
    #set to TRUE if you want it OA_CACHE to append an object pk
    object_specific = models.BooleanField(default=False)
    #if this usersalt is associated with a different context, we need to redirect to that context
    redirect = models.BooleanField(default=False)
    #if this userSalt object is only used in a single page
    #we want all other views to turn off the user salt, by replacing it with an empty salt
    #thus if this model_cache is OPPOSITE, the model cache is the only one that doesn't
    #render an empty in this DIV_ID
    opposite = models.BooleanField(default=False)
    #should we cache this non-dynamic html?
    cache = models.BooleanField(default=False)
    ###does this object need to be loaded last on the page, for instance if an anchor needs to be placed first
    load_last = models.BooleanField(default=False)
    ###if we should only load when the user prompts us to load
    persistent = models.BooleanField(default=False)
    ###persistent to a single dashboard

    def recursive_render(self, tree, context):
        ret_html = []
        for obj in tree:
            if isinstance(obj, list):
                context['object'] = obj[0]
                #context['count'] = len(tree[1])
                ret_html.append((render_to_string(self.template, context), obj[0].pk))
                if len(obj) > 1:
                    ret_html.extend(self.recursive_render(obj[1], context))
            else:
                context['object'] = obj
                #context['count'] = 0
                ret_html.append((render_to_string(self.template, context), obj.pk))
        return ret_html

    def render(self, context, forcerender=True):
        if not self.is_recursive:
            if self.cache:
                key = str(context['object'].pk) + ' - ' + self.template.replace('/','-').replace('.', '-').replace('_', '-')
                cached = memcache.get(key)
                if cached == None or forcerender:
                    r = render_to_string(self.template, context)
                    memcache.set(key, r)
                    return r
                else:
                    return cached
            return render_to_string(self.template, context)
        else:
            obj = self.recursive_render([context['object']], context)
            return obj

    def __unicode__(self):
        return '%s %s %s' % (self.template, self.div_id, str(self.pk))


class SideEffectCache(models.Model):
    """User salt renders based on object and user,
only rendered when the corresponding model_cache is rendered"""
    user_salt_cache = models.CharField('Object_ID', max_length=100)
    template = models.CharField(max_length=200)
    div_id = models.CharField(max_length=200)
    jquery_cmd = models.CharField(max_length=200)
    #is this object DIV specific or required an object pk appended
    #set to TRUE if you want it OA_CACHE to append an object pk
    object_specific = models.BooleanField(default=False)
    key_specific = models.BooleanField(default=False)
    scroll_to = models.BooleanField(default=True)

    def render(self, context):
        return render_to_string(self.template, context)

    def __unicode__(self):
        return 'USC : %s -- (%s %s)' % (self.user_salt_cache, self.template, self.div_id)
