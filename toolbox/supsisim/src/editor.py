from pyqt5  import QMenu, QGraphicsItem, QtCore, QTransform

from supsisim.port import Port, InPort, OutPort
from supsisim.connection import Connection
from supsisim.block import Block
from supsisim.dialg import BlockName_Dialog
import supsisim.RCPDlg as pDlg
from supsisim.const import GRID, DB
from supsisim.node import Node
import numpy as np

# States
IDLE = 0
LEFTMOUSEPRESSED = 1
ITEMSELECTED = 2
DRAWFROMOUTPORT = 3
MOVECONN = 4

MOUSEMOVE = 0
LEFTMOUSEPRESSED = 1
RIGHTMOUSEPRESSED = 2
MOUSERELEASED = 3
MOUSEDOUBLECLICK = 4
KEY_DEL = 5
KEY_ESC = 6
    
class Editor(QtCore.QObject):
    """ Editor to handles events"""
    def __init__(self, parent):
        super(Editor, self).__init__(parent)
        self.conn = None
        self.scene = None
        self.movBlk = False
        self.event = None
        self.state = IDLE

        self.menuIOBlk = QMenu()
        parBlkAction = self.menuIOBlk.addAction('Block I/Os')
        paramsBlkAction = self.menuIOBlk.addAction('Block Parameters')
        flpBlkAction = self.menuIOBlk.addAction('Flip Block')
        nameBlkAction = self.menuIOBlk.addAction('Change Name')
        cloneBlkAction = self.menuIOBlk.addAction('Clone Block')
        deleteBlkAction = self.menuIOBlk.addAction('Delete Block')
        
        parBlkAction.triggered.connect(self.parBlock)
        flpBlkAction.triggered.connect(self.flipBlock)
        nameBlkAction.triggered.connect(self.nameBlock)
        paramsBlkAction.triggered.connect(self.paramsBlock)
        cloneBlkAction.triggered.connect(self.cloneBlock)
        deleteBlkAction.triggered.connect(self.deleteBlock)

        self.subMenuConn = QMenu()
        connAddAction = self.subMenuConn.addAction('Add connection')
        connDelAction = self.subMenuConn.addAction('Delete connection')
        connAddAction.triggered.connect(self.addConn)
        connDelAction.triggered.connect(self.deleteConn)

        # Matrix has two index [state, event]
        # States:
        # IDLE                                  0
        # LEFTMOUSEPRESSED       1
        # ITEMSELECTED                 2
        # DRAWFROMOUTPORT      3
        # MOVECONN                      4
        
        # Events
        # MOUSEMOVE                    0
        # LEFTMOUSEPRESSED        1
        # RIGHTMOUSEPRESSED     2
        # MOUSERELEASED             3
        # MOUSEDOUBLECLICK       4
        # KEY_DEL                            5
        # KEY_ESC                            6

        self.Fun = [[self.P00, self.P01, self.P02, self.PDM, self.P03, self.P04, self.P05],
                        [self.P06, self.PDM, self.PDM, self.P07, self.PDM, self.PDM, self.PDM],
                        [self.P11, self.P01, self.P02, self.PDM, self.P03, self.P04, self.P05],
                        [self.P10, self.P08, self.P09, self.PDM, self.PDM, self.PDM, self.P09],
                        [self.P12, self.PDM, self.PDM, self.P13, self.PDM, self.PDM, self.PDM]]
              
    def install(self, scene):
        scene.installEventFilter(self)
        self.scene = scene
    
    def parBlock(self):
        self.scene.DgmToUndo()
        ok = self.scene.mainw.parBlock()
        if not ok:
            self.scene.clearLastUndo()
    
    def flipBlock(self):
        self.scene.DgmToUndo()
        item = self.scene.item
        item.flip = not item.flip
        item.setFlip()
        
    def nameBlock(self):
        self.scene.DgmToUndo()
        item = self.scene.item
        dialog = BlockName_Dialog(self.scene.mainw)
        dialog.name.setText(item.name)
        res = dialog.exec_()
        if res == 1:
            item.name = str(dialog.name.text())
            item.label.setPlainText(item.name)
            w = item.label.boundingRect().width()
            item.label.setPos(-w/2, item.h/2+5)
        else:
            self.scene.clearLastUndo()
        
    def paramsBlock(self):
        self.scene.DgmToUndo()
        item = self.scene.item
        params = item.params.split('|')
        blk = params[0]
        blk = blk.replace('Blk','Dlg')
        if blk in dir(pDlg):
            name =  item.name.replace(' ','_')
            cmd = 'pDlg.' + blk + '(' + str(item.inp) + ',' + str(item.outp) + ',"' + item.params + '"' +  ',"' +  name + '")'
            pars = eval(cmd)
        else:
            pars = pDlg.parsDialog(item.params)
        if pars != item.params:
            item.params = pars
        else:
            self.scene.clearLastUndo()

    def cloneBlock(self):
        self.scene.DgmToUndo()
        item = self.scene.item
        item.clone(QtCore.QPointF(100,100))

    def deleteBlock(self):
        self.scene.DgmToUndo()
        item = self.scene.item
        item.remove()

    def connectInPort(self, item):
        if len(item.connections)==0:
            self.conn.port2 = item
            self.conn.pos2 = item.scenePos()
            self.conn.port1.connections.append(self.conn)
            self.conn.port2.connections.append(self.conn)
            if len(self.conn.connPoints) == 0:
                pos1 = QtCore.QPointF((self.conn.pos2.x()+self.conn.pos1.x())/2, self.conn.pos1.y())
                pos2 = QtCore.QPointF((self.conn.pos2.x()+self.conn.pos1.x())/2, self.conn.pos2.y())
                self.conn.connPoints.append(self.gridPos(pos1))
                self.conn.connPoints.append(self.gridPos(pos2))
            else:
                pt = self.conn.connPoints[-1]
                pos1 = QtCore.QPointF((self.conn.pos2.x()+pt.x())/2, pt.y())
                pos2 = QtCore.QPointF((self.conn.pos2.x()+pt.x())/2, self.conn.pos2.y())
                self.conn.connPoints.append(self.gridPos(pos1))
                self.conn.connPoints.append(self.gridPos(pos2))
        self.conn.update_path()
        self.conn = None
 
    def deleteConn(self):
        self.scene.DgmToUndo()
        self.scene.item.remove()
        self.redrawNodes()

    def find_exact_pos(self, c, pos):
        # Find exact point on connection c
        points = [c.pos1]
        for el in c.connPoints:
            points.append(el)
        points.append(c.pos2)
        N = len(points)
        for n in range(0,N-1):
            p1 = points[n]
            p2 = points[n+1]
            rect = QtCore.QRectF(p1 - QtCore.QPointF(DB,DB) ,p2 + QtCore.QPointF(DB,DB))
            if rect.contains(pos):
                if p1.x() == p2.x():
                    pos.setX(p1.x())
                if p1.y() == p2.y():
                    pos.setY(p1.y())
                return n, pos
        
    def addConn(self):
        self.scene.DgmToUndo()
        c = self.scene.item
        posMouse = self.gridPos(self.scene.evpos)
        self.conn = Connection(None, self.scene)
        self.conn.port1 = c.port1
        self.conn.pos1 = c.pos1

        try:
            npos, pos = self.find_exact_pos(c, posMouse)
        except:
            return
        N = len(c.connPoints)
        
        if npos == 0:
            pos = posMouse
            npt = 0
        elif npos == N:
            pos = posMouse
            npt = N
        else:            
            npt = npos
       
        for n in range(0, npt):
            self.conn.connPoints.append(c.connPoints[n])
        self.conn.connPoints.append(pos)
        self.state = DRAWFROMOUTPORT

    def redrawSelectedItems(self):
        for item in self.scene.selectedItems():
            if isinstance(item, Block):
                item.setPos(item.scenePos())
                for el in item.childItems():
                    try:
                        for conn in el.connections:
                            conn.update_pos_from_ports()
                    except:
                        pass

    def setNode(self, pts1, pts2):
        # Eliminate points in straight segments
        N = len(pts1)
        remPt = []
        for n in range(1,N-1):
            if pts1[n-1].x() == pts1[n].x() == pts1[n+1].x() or\
               pts1[n-1].y() == pts1[n].y() == pts1[n+1].y():
                remPt.append(pts1[n])
        for el in remPt:
            pts1.remove(el)
            
        N = len(pts2)
        remPt = []
        for n in range(1,N-1):
            if pts2[n-1].x() == pts2[n].x() == pts2[n+1].x() or\
               pts2[n-1].y() == pts2[n].y() == pts2[n+1].y():
                remPt.append(pts2[n])
        for el in remPt:
            pts2.remove(el)
            
        n = 0
        N = min(len(pts1), len(pts2))
        while pts1[n] == pts2[n] and n <N:
            n +=1
        p11 = pts1[n-1]
        p12 = pts1[n]
        p21 = pts2[n-1]
        p22 = pts2[n]
        l1 = QtCore.QLineF(p11,p12)
        l2 = QtCore.QLineF(p21,p22)
        d1 = p12 - p11
        d2 = p22 - p21
        if d1.x()*d2.x() < 0 or d1.y()*d2.y() < 0:
            pos = p11        
        else:
            if  l1.length() <= l2.length():
                pos = p12
            else:
                pos = p22
                
        node = Node(None, self.scene)
        node.setPos(pos)
        
    def redrawNodes(self):
        for el in self.scene.items():
            if isinstance(el, Node):
                el.remove()
        for item in self.scene.items():
            if isinstance(item, Block):
                for p in item.childItems():
                    if isinstance(p, OutPort):
                        N = len(p.connections)
                        for n in range(0,N):
                            pts1 = [p.connections[n].pos1]
                            for el in p.connections[n].connPoints:
                                pts1.append(el)
                            pts1.append(p.connections[n].pos2)
                            for m in range(n+1,N):
                                pts2 = [p.connections[m].pos1]
                                for el in p.connections[m].connPoints:
                                    pts2.append(el)
                                pts2.append(p.connections[m].pos2)
                                
                                self.setNode(pts1, pts2)
                                           
    def itemAt(self, pos):
        rect = QtCore.QRectF(pos+QtCore.QPointF(-DB,-DB), QtCore.QSizeF(2*DB,2*DB))
        items =  self.scene.items(rect)

        for item in items:
            if isinstance(self.findBlockAt(pos), Block):
                return item
        for item in items:
            if isinstance(self.findOutPortAt(pos), OutPort):
                return item
        for item in items:
            if isinstance(self.findInPortAt(pos), InPort):
                return(item)
        for item in items:
            if isinstance(self.findConnectionAt(pos), Connection):
                return(item)
        return None

    def itemByDraw(self, pos):
        rect = QtCore.QRectF(pos-QtCore.QPointF(DB,DB), QtCore.QSizeF(2*DB,2*DB))
        items =  self.scene.items(QtCore.QRectF(pos-QtCore.QPointF(DB,DB), QtCore.QSizeF(2*DB,2*DB)))
        for item in items:
            if isinstance(item, InPort):
                return(item)
        return None
    
    def findInPortAt(self, pos):
        items =  self.scene.items(QtCore.QRectF(pos-QtCore.QPointF(DB,DB), QtCore.QSizeF(2*DB,2*DB)))
        for el in items:
            if isinstance(el, InPort):
                return el
        return None

    def findOutPortAt(self, pos):
        items =  self.scene.items(QtCore.QRectF(pos-QtCore.QPointF(DB,DB), QtCore.QSizeF(2*DB,2*DB)))
        for el in items:
            if isinstance(el, OutPort):
                return el
        return None

    def findBlockAt(self, pos):
        items =  self.scene.items(QtCore.QRectF(pos-QtCore.QPointF(DB,DB), QtCore.QSizeF(2*DB,2*DB)))
        for el in items:
            if isinstance(el, Block):
                return el
        return None

    def findConnectionAt(self, pos):
        items =  self.scene.items(QtCore.QRectF(pos-QtCore.QPointF(DB,DB), QtCore.QSizeF(2*DB,2*DB)))
        for c in items:
            if isinstance(c, Connection):
                points = [c.pos1]
                for el in c.connPoints:
                    points.append(el)
                points.append(c.pos2)
                N = len(points)
                for n in range(0,N-1):
                    p1 = points[n]
                    p2 = points[n+1]
                    rect = QtCore.QRectF(p1 - QtCore.QPointF(DB,DB) ,p2 + QtCore.QPointF(DB,DB))
                    if rect.contains(pos):
                        return c
        return None
 
    def deselect_all(self):
        for el in self.scene.items():
            el.setSelected(False)

    def setMouseInitDraw(self, pos):
        pointer = QtCore.Qt.ArrowCursor
        if isinstance(self.findBlockAt(pos), Block):
            pointer = QtCore.Qt.ArrowCursor
        elif isinstance(self.findOutPortAt(pos), OutPort):
            pointer = QtCore.Qt.CrossCursor
        elif isinstance(self.findConnectionAt(pos), Connection):
            pointer = QtCore.Qt.PointingHandCursor
        else:
            pointer = QtCore.Qt.ArrowCursor
        self.scene.mainw.view.setCursor(pointer)        
            
    def setMouseByDraw(self, item):
        if isinstance(item, InPort) and len(item.connections)==0:
            pointer = QtCore.Qt.CrossCursor
        else:
            pointer = QtCore.Qt.DragLinkCursor
        self.scene.mainw.view.setCursor(pointer)        
            
    def PDM(self, obj, event):    # Dummy function - No action
        pass

    def P00(self, obj, event):                                   # IDLE + MOUSEMOVE
        self.setMouseInitDraw(event.scenePos())
        
        item = self.itemAt(event.scenePos())
        if item == None:
            self.deselect_all()
        else:
            try:
                item.setSelected(True)
            except:
                pass
        self.scene.updateDgm()
 
    def P01(self, obj, event):                                     # IDLE, ITEMSELECTED + LEFTMOUSEPRESSED
        item = self.findConnectionAt(event.scenePos())
        if item != None:
            self.scene.currentItem = item
            self.currentPos = event.scenePos()
            self.deselect_all()
            self.scene.DgmToUndo()
            self.state = MOVECONN
        else:
            self.state = LEFTMOUSEPRESSED
            
    def P02(self, obj, event):                                     # IDLE, ITEMSELECTED + RIGHTMOUSEPRESSED
        item = self.findBlockAt(event.scenePos())
        self.deselect_all()
        if isinstance(item, Block):
            item.setSelected(True)
            self.scene.item = item
            self.scene.evpos = event.scenePos()
            try:
                self.menuIOBlk.exec_(event.screenPos())
            except:
                pass
        else:                
            item = self.findConnectionAt(event.scenePos())
            if isinstance(item,Connection):
                self.scene.item = item
                self.scene.evpos = event.scenePos()
                try:
                    self.subMenuConn.exec_(event.screenPos())
                except:
                    pass

    def P03(self, obj, event):                                     # IDLE, ITEMSELECTED + MOUSEDOUBLECLICK
        item = self.findBlockAt(event.scenePos())
        self.deselect_all()
        if isinstance(item, Block):
            item.setSelected(True)
            self.scene.item = item
            self.scene.evpos = event.scenePos()
            self.paramsBlock()

    def P04(self, obj, event):                                     # ITEMSELECTED + KEY_DEL
        items = self.scene.selectedItems()
        self.scene.DgmToUndo()
        for item in items:
            try:
                item.remove()
            except:
                pass
        self.state = IDLE

    def P05(self, obj, event):                                     # ITEMSELECTED + KEY_ESC
        self.state = IDLE

    def P06(self, obj, event):                                     # LEFTMOUSEPRESSED + MOUSEMOVE
        self.redrawSelectedItems()
        self.redrawNodes()
        item = self.itemAt(event.scenePos())
                        
    def P07(self, obj, event):                                      # LEFTMOUSEPRESSED + MOUSERELEASED
        self.redrawSelectedItems()
        self.redrawNodes()
        
        item = self.itemAt(event.scenePos())
        if self.scene.currentItem != None:
            self.scene.currentItem = None
            self.deselect_all()
            try:
                item.setSelected(True)
                self.scene.currentItem = item
            except:
                pass        

        if self.scene.selectedItems():
            self.state = ITEMSELECTED
        else:
            self.state = IDLE

        if isinstance(item, OutPort):            
            self.scene.DgmToUndo()
            self.state = DRAWFROMOUTPORT
            self.conn = Connection(None, self.scene)
            self.conn.port1 = item
            self.conn.pos1 = item.scenePos()
            self.conn.pos2 = item.scenePos()

    def P08(self, obj, event):                                      # DRAWFROMOUTPORT + LEFTMOUSEPRESSED
        item = self.findInPortAt(event.scenePos())
        if isinstance(item,InPort):
            self.connectInPort(item)
            self.redrawNodes()
            self.state = IDLE
        else:
            pt = self.gridPos(event.scenePos())
            self.conn.addPoint(pt)
            self.conn.pos2 = pt            
            self.conn.update_path()
                    
    def P09(self, obj, event):                                      # DRAWFROMOUTPORT + RIGHTMOUSEPRESSED, KEY_ESC
        try:
            self.conn.remove()
            self.scene.undoDgm()
        except:
            pass
        self.conn = None
        self.state = IDLE
       
    def P10(self, obj, event):                                      # DRAWFROMOUTPORT + MOUSEMOVE
        item = self.itemByDraw(event.scenePos())
        self.setMouseByDraw(item)
        self.conn.pos2 = event.scenePos()
        if isinstance(item, InPort):
            self.conn.update_path('movPort')
        else:
            self.conn.update_path('moving')
                    
    def P11(self, obj, event):                                      # ITEMSELECTED + MOUSEMOVE
        self.setMouseInitDraw(event.scenePos())

    def P12(self, obj, event):                                      # MOVECONN + MOUSEMOVE
        item = self.scene.currentItem
        N = len(item.connPoints)
        oldPos = self.currentPos
        newPos = self.gridPos(event.scenePos())
        try:
            npos, pos = self.find_exact_pos(item, oldPos)
        except:
            return
            
        if npos != 0 and npos != N:
            ok = item.move(npos, newPos)
            if ok:
                self.currentPos = newPos

    def P13(self, obj, event):
        item = self.scene.currentItem
        N = len(item.connPoints)
        oldPos = self.currentPos
        newPos = self.gridPos(event.scenePos())
        try:
            npos, pos = self.find_exact_pos(item, oldPos)
        except:
            return
            
        if npos != 0 and npos != N:
            ok = item.move(npos, newPos)
            if ok:
                self.currentPos = newPos

        self.redrawNodes()
        self.scene.currentItem = None
        self.state = IDLE
        
    def eventFilter(self, obj, event):
        ev = -1
        if event.type() ==  QtCore.QEvent.GraphicsSceneMouseMove:
            ev = 0
             
        if event.type() ==  QtCore.QEvent.GraphicsSceneMousePress:
            if event.button() == QtCore.Qt.LeftButton:
                ev = 1
            if event.button() == QtCore.Qt.RightButton:
                ev = 2
        
        if event.type() == QtCore.QEvent.GraphicsSceneMouseRelease:
            ev = 3
                
        if event.type() == QtCore.QEvent.GraphicsSceneMouseDoubleClick:
            ev = 4

        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Delete:
                ev = 5
            if event.key() == QtCore.Qt.Key_Escape:
                ev = 6
        if ev != -1:
            #print('state->', self.state, 'event->',ev)
            fun = self.Fun[self.state][ ev]
            fun(obj, event)
                
        return False

    def gridPos(self, pt):
         gr = GRID
         x = gr * ((pt.x() + gr /2) // gr)
         y = gr * ((pt.y() + gr /2) // gr)
         return QtCore.QPointF(x,y)

