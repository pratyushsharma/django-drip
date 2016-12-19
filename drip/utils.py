import sys

from django.db import models
from django.db.models import ForeignKey, OneToOneField, ManyToManyField
# try:
#    from django.db.models.related import RelatedObject
# except:
#   # django 1.8 +
from django.db.models.fields.related import ForeignObjectRel

from pyparsing import Literal,CaselessLiteral,Word,Combine,Group,Optional,\
    ZeroOrMore,Forward,nums,alphas

# taking a nod from python-requests and skipping six
_ver = sys.version_info
is_py2 = (_ver[0] == 2)
is_py3 = (_ver[0] == 3)

if is_py2:
    basestring = basestring
    unicode = unicode
elif is_py3:
    basestring = (str, bytes)
    unicode = str


def get_fields(Model,
               parent_field="",
               model_stack=None,
               stack_limit=2,
               excludes=['permissions', 'comment', 'content_type']):
    """
    Given a Model, return a list of lists of strings with important stuff:
    ...
    ['test_user__user__customuser', 'customuser', 'User', 'RelatedObject']
    ['test_user__unique_id', 'unique_id', 'TestUser', 'CharField']
    ['test_user__confirmed', 'confirmed', 'TestUser', 'BooleanField']
    ...

     """
    out_fields = []

    if model_stack is None:
        model_stack = []

    # github.com/omab/python-social-auth/commit/d8637cec02422374e4102231488481170dc51057
    if isinstance(Model, basestring):
        app_label, model_name = Model.split('.')
        Model = models.get_model(app_label, model_name)

    #fields = Model._meta.fields + Model._meta.many_to_many + tuple(Model._meta.get_all_related_objects())
    fields = Model._meta.get_fields()
    model_stack.append(Model)

    # do a variety of checks to ensure recursion isnt being redundant

    stop_recursion = False
    if len(model_stack) > stack_limit:
        # rudimentary CustomUser->User->CustomUser->User detection
        if model_stack[-3] == model_stack[-1]:
            stop_recursion = True

        # stack depth shouldn't exceed x
        if len(model_stack) > 5:
            stop_recursion = True

        # we've hit a point where we are repeating models
        if len(set(model_stack)) != len(model_stack):
            stop_recursion = True

    if stop_recursion:
        return [] # give empty list for "extend"

    for field in fields:
        field_name = field.name

        # if instance(field, Man)

        if isinstance(field, ForeignObjectRel):
            # from pdb import set_trace
            # set_trace()
            # print (field, type(field))
            field_name = field.field.related_query_name()

        if parent_field:
            full_field = "__".join([parent_field, field_name])
        else:
            full_field = field_name

        # print (field, field_name, full_field)

        if len([True for exclude in excludes if (exclude in full_field)]):
            continue

        # add to the list
        out_fields.append([full_field, field_name, Model, field.__class__])

        if not stop_recursion and \
                isinstance(field, ForeignObjectRel):
                # (isinstance(field, ForeignKey) or isinstance(field, OneToOneField) or \
                # isinstance(field, RelatedObject) or isinstance(field, ManyToManyField)):

            # from pdb import set_trace
            # set_trace()
            if not isinstance(field, ForeignObjectRel):
                RelModel = field.model
            else:
                RelModel = field.related_model
            # print (RelModel)
            # if isinstance(field, RelatedObject):
            #     RelModel = field.model
            #     #field_names.extend(get_fields(RelModel, full_field, True))
            # else:
            #     RelModel = field.related.parent_model

            out_fields.extend(get_fields(RelModel, full_field, list(model_stack)))

    return out_fields

def give_model_field(full_field, Model):
    """
    Given a field_name and Model:

    "test_user__unique_id", <AchievedGoal>

    Returns "test_user__unique_id", "id", <Model>, <ModelField>
    """
    field_data = get_fields(Model, '', [])

    for full_key, name, _Model, _ModelField in field_data:
        if full_key == full_field:
            return full_key, name, _Model, _ModelField

    raise Exception('Field key `{0}` not found on `{1}`.'.format(full_field, Model.__name__))

def get_simple_fields(Model, **kwargs):
    return [[f[0], f[3].__name__] for f in get_fields(Model, **kwargs)]

def get_user_model():
    # handle 1.7 and back
    try:
        from django.contrib.auth import get_user_model as django_get_user_model
        User = django_get_user_model()
    except ImportError:
        from django.contrib.auth.models import User
    return User








class RuleEvaluator:

    def get_Q(self, arg):
        """
        """
        if not isinstance(arg, unicode):
            return arg
        Q_arg = models.Q(self.clause[int(arg)-1][0]) if self.clause[int(arg)-1][1] == 'filter'\
         else ~models.Q(self.clause[int(arg)-1][0])
        return Q_arg

    def apply_or(self, arg1, arg2):
        """
        Takes two arguments and applies | between them
        """
        return (arg1 | arg2)

    def apply_and(self, arg1, arg2):
        """
        Takes two arguments and applies & between them
        """
        return (arg1 & arg2)

    def __init__(self, clause):
        self.clause = clause
        self.opn = {"|" : self.apply_or, "&" : self.apply_and}
        self.exprStack = []
        self.bnf = None


    def pushFirst(self, strg, loc, toks ):
        self.exprStack.append( toks[0] )

    def BNF(self):
        if not self.bnf:
            fnumber = Combine( Word( "+-"+nums, nums ) +
                               Optional( Optional( Word( nums ) ) ) +
                               Optional( Word( "+-"+nums, nums ) ) )
            ident = Word(alphas, alphas+nums+"_$")

            lpar  = Literal( "(" ).suppress()
            rpar  = Literal( ")" ).suppress()
            orop  = Literal( "|" )
            andop = Literal( "&" )

            expr = Forward()
            atom = ( fnumber | ident + lpar + expr + rpar ).setParseAction( self.pushFirst ) | ( lpar + expr.suppress() + rpar )

            factor = Forward()
            factor << atom

            term = factor + ZeroOrMore( ( andop + factor ).setParseAction( self.pushFirst ) )
            expr << term + ZeroOrMore( ( orop + term ).setParseAction( self.pushFirst ) )
            self.bnf = expr
        return self.bnf

    def evaluateStack(self, s=None):
        if s == None:
            s = self.exprStack
        op = s.pop()
        if op in "|&":
            op2 = self.evaluateStack( s )
            op1 = self.evaluateStack( s )
            return self.opn[op]( op1, op2 )
        else:
            return self.get_Q(op)