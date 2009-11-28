"""
property_manager
================

:Author: Ho Chun Wei, fuzzybr80(at)gmail.com (author of original PyFileServer)
:Author: Martin Wendt, moogle(at)wwwendt.de 
:Copyright: Lesser GNU Public License, see LICENSE file attached with package

Implements two property managers: one in-memory (dict-based), and one 
persistent low performance variant using shelve.

This module consists of a number of miscellaneous functions for the dead 
properties features of WebDAV.

It also includes an implementation of a PropertyManager for
storage of dead properties. This implementation use
shelve for file storage.  See request_server.py for details.

PropertyManagers must provide the methods as described in 
propertymanagerinterface_

See DEVELOPERS.txt_ for more information about the WsgiDAV architecture.

.. _DEVELOPERS.txt: http://wiki.wsgidav-dev.googlecode.com/hg/DEVELOPERS.html  
.. _propertymanagerinterface : interfaces/propertymanagerinterface.py



Properties and WsgiDAV
----------------------
Properties of a resource refers to the attributes of the resource. A property
is referenced by the property name and the property namespace. We usually
refer to the property as ``{property namespace}property name`` 

Properties of resources as defined in WebDAV falls under three categories:

Live properties
   These properties are attributes actively maintained by the server, such as 
   file size, or read permissions. if you are sharing a database record as a 
   resource, for example, the attributes of the record could become the live 
   properties of the resource.

   The webdav specification defines the following properties that could be
   live properties (refer to webdav specification for details):
   {DAV:}creationdate
   {DAV:}displayname
   {DAV:}getcontentlanguage
   {DAV:}getcontentlength
   {DAV:}getcontenttype
   {DAV:}getetag
   {DAV:}getlastmodified
   {DAV:}resourcetype
   {DAV:}source

   These properties are implemented by the abstraction layer.

Locking properties 
   They refer to the two webdav-defined properties 
   {DAV:}supportedlock and {DAV:}lockdiscovery
    
   These properties are implemented by the locking library in
   ``wsgidav.lock_manager``.
      
Dead properties
   They refer to arbitrarily assigned properties not actively maintained. 

   These properties are implemented by the dead properties library in
   ``wsgidav.property_manager``.
"""
from wsgidav import util
import os
import sys
import shelve
from rw_lock import ReadWriteLock

# TODO: comment's from Ian Bicking (2005)
#@@: Use of shelve means this is only really useful in a threaded environment.
#    And if you have just a single-process threaded environment, you could get
#    nearly the same effect with a dictionary of threading.Lock() objects.  Of course,
#    it would be better to move off shelve anyway, probably to a system with
#    a directory of per-file locks, using the file locking primitives (which,
#    sadly, are not quite portable).
# @@: It would probably be easy to store the properties as pickle objects
# in a parallel directory structure to the files you are describing.
# Pickle is expedient, but later you could use something more readable
# (pickles aren't particularly readable)

__docformat__ = "reStructuredText"

_logger = util.getModuleLogger(__name__)


    
#===============================================================================
# PropertyManager
#===============================================================================
class PropertyManager(object):
    """
    An in-memory property manager implementation using a dictionary.
    
    This is obviously not persistent, but should be enough in some cases.
    For a persistent implementation, see property_manager.ShelvePropertyManager().
    """
    def __init__(self):
        self._dict = None
        self._loaded = False      
        self._lock = ReadWriteLock()
        self._verbose = 2


    def __repr__(self):
        return "PropertyManager"


    def __del__(self):
        if __debug__ and self._verbose >= 2:
            self._check()         
        self._close()


    def _lazyOpen(self):
        _logger.debug("_lazyOpen()")
        self._lock.acquireWrite()
        try:
            self._dict = {}
            self._loaded = True
        finally:
            self._lock.release()         


    def _sync(self):
        pass

    
    def _close(self):
        _logger.debug("_close()")
        self._lock.acquireWrite()
        try:
            self._dict = None
            self._loaded = False
        finally:
            self._lock.release()         

    
    def _check(self, msg=""):
        try:
            if not self._loaded:
                return True
#            for k in self._dict.keys():
#                print "%s" % k
#                print "  -> %s" % self._dict[k]
            for k, v in self._dict.items():
                _ = "%s, %s" % (k, v)
            _logger.debug("%s checks ok %s" % (self.__class__.__name__, msg))
            return True
        except Exception:
            _logger.exception("%s _check: ERROR %s" % (self.__class__.__name__, msg))
#            traceback.print_exc()
#            raise
#            sys.exit(-1)
            return False


    def _dump(self, msg="", out=None):
        if out is None:
            out = sys.stdout
        print >>out, "%s(%s): %s" % (self.__class__.__name__, self.__repr__(), msg)
        if not self._loaded:
            self._lazyOpen()
            if self._verbose >= 2:
                return # Already dumped in _lazyOpen
        try:
            for k, v in self._dict.items():
                print >>out, "    ", k
                for k2, v2 in v.items():
                    try:
                        print >>out, "        %s: '%s'" % (k2, v2)
                    except Exception, e:
                        print >>out, "        %s: ERROR %s" % (k2, e)
        except Exception, e:
            print >>sys.stderr, "PropertyManager._dump()  ERROR: %s" % e            


    def getProperties(self, normurl):
        _logger.debug("getProperties(%s)" % normurl)
        self._lock.acquireRead()
        try:
            if not self._loaded:
                self._lazyOpen()        
            returnlist = []
            if normurl in self._dict:
                for propdata in self._dict[normurl].keys():
                    returnlist.append(propdata)
            return returnlist
        finally:
            self._lock.release()


    def getProperty(self, normurl, propname):
        _logger.debug("getProperty(%s, %s)" % (normurl, propname))
        self._lock.acquireRead()
        try:
            if not self._loaded:
                self._lazyOpen()
            if normurl not in self._dict:
                return None
            # TODO: sometimes we get exceptions here: (catch or otherwise make more robust?)
            try:
                resourceprops = self._dict[normurl]
            except Exception, e:
                _logger.exception("getProperty(%s, %s) failed : %s" % (normurl, propname, e))
                raise
            return resourceprops.get(propname)
        finally:
            self._lock.release()


    def writeProperty(self, normurl, propname, propertyvalue, dryRun=False):
#        self._log("writeProperty(%s, %s, dryRun=%s):\n\t%s" % (normurl, propname, dryRun, propertyvalue))
        assert normurl and normurl.startswith("/")
        assert propname #and propname.startswith("{")
        assert propertyvalue is not None
        
        _logger.debug("writeProperty(%s, %s, dryRun=%s):\n\t%s" % (normurl, propname, dryRun, propertyvalue))
        if dryRun:
            return  # TODO: can we check anything here?
        
        self._lock.acquireWrite()
        try:
            if not self._loaded:
                self._lazyOpen()
            if normurl in self._dict:
                locatordict = self._dict[normurl] 
            else:
                locatordict = {} #dict([])    
            locatordict[propname] = propertyvalue
            # This re-assignment is important, so Shelve realizes the change:
            self._dict[normurl] = locatordict
            self._sync()
            if __debug__ and self._verbose >= 2:
                self._check()         
        finally:
            self._lock.release()


    def removeProperty(self, normurl, propname, dryRun=False):
        """
        Specifying the removal of a property that does not exist is NOT an error.
        """
        _logger.debug("removeProperty(%s, %s, dryRun=%s)" % (normurl, propname, dryRun))
        if dryRun:
            # TODO: can we check anything here?
            return  
        self._lock.acquireWrite()
        try:
            if not self._loaded:
                self._lazyOpen()
            if normurl in self._dict:      
                locatordict = self._dict[normurl] 
                if propname in locatordict:
                    del locatordict[propname]
                    # This re-assignment is important, so Shelve realizes the change:
                    self._dict[normurl] = locatordict
                    self._sync()
            if __debug__ and self._verbose >= 2:
                self._check()         
        finally:
            self._lock.release()         


    def removeProperties(self, normurl):
        _logger.debug("removeProperties(%s)" % normurl)
        self._lock.acquireWrite()
        try:
            if not self._loaded:
                self._lazyOpen()
            if normurl in self._dict:      
                del self._dict[normurl] 
                self._sync()
        finally:
            self._lock.release()         


    def copyProperties(self, srcurl, desturl):
        _logger.debug("copyProperties(%s, %s)" % (srcurl, desturl))
        self._lock.acquireWrite()
        try:
            if __debug__ and self._verbose >= 2:
                self._check()         
            if not self._loaded:
                self._lazyOpen()
            if srcurl in self._dict:      
                self._dict[desturl] = self._dict[srcurl].copy() 
                self._sync()
            if __debug__ and self._verbose >= 2:
                self._check("after copy")         
        finally:
            self._lock.release()         


#===============================================================================
# ShelvePropertyManager
#===============================================================================

class ShelvePropertyManager(PropertyManager):
    """
    A low performance property manager implementation using shelve
    """
    def __init__(self, storagePath):
        self._storagePath = os.path.abspath(storagePath)
        super(ShelvePropertyManager, self).__init__()


    def __repr__(self):
        return "ShelvePropertyManager(%s)" % self._storagePath
        

    def _lazyOpen(self):
        _logger.debug("_lazyOpen(%s)" % self._storagePath)
        self._lock.acquireWrite()
        try:
            # Test again within the critical section
            if self._loaded:
                return True
            # Open with writeback=False, which is faster, but we have to be 
            # careful to re-assign values to _dict after modifying them
            self._dict = shelve.open(self._storagePath, 
                                     writeback=False)
            self._loaded = True
            if __debug__ and self._verbose >= 2:
                self._check("After shelve.open()")
                self._dump("After shelve.open()")
        finally:
            self._lock.release()         


    def _sync(self):
        """Write persistent dictionary to disc."""
        _logger.debug("_sync()")
        self._lock.acquireWrite() # TODO: read access is enough?
        try:
            if self._loaded:
                self._dict.sync()
        finally:
            self._lock.release()         


    def _close(self):
        _logger.debug("_close()")
        self._lock.acquireWrite()
        try:
            if self._loaded:
                self._dict.close()
                self._dict = None
                self._loaded = False
        finally:
            self._lock.release()         