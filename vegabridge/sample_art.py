"""Original geometric sample icons, drawn locally without external assets."""
import math
from pathlib import Path
from PySide6.QtGui import QImage,QPainter,QColor,QPen,QPolygonF,QPainterPath
from PySide6.QtCore import QPointF,QRectF,Qt

PALETTES=[('#101d27','#f2b66c'),('#efe4cf','#657c47'),('#092d52','#7bd5ff'),('#030d08','#47ff83'),
 ('#f1efde','#728d40'),('#201d38','#c3a0ff'),('#244749','#e5c47e'),('#e5e9f4','#8b87be'),
 ('#ffe4c8','#c44081'),('#291d2d','#f0b976'),('#f5d95e','#327c82'),('#182f2c','#d0b56b'),
 ('#21112e','#ff82ca'),('#e8ded1','#b54c3f'),('#113f38','#e1ca7e'),('#241a23','#ffb567'),
 ('#e7efd1','#678f49'),('#172238','#e6b9a0'),('#2d2354','#d7bcff'),('#badddf','#287c8c')]


def draw_icon(destination,index,size=512):
    bg,accent=PALETTES[index%20];image=QImage(size,size,QImage.Format.Format_ARGB32);image.fill(QColor(bg))
    p=QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.scale(size/512,size/512)
    p.setPen(QPen(QColor(accent),12,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    def line(x,y,a,b):p.drawLine(QPointF(x,y),QPointF(a,b))
    def rect(x,y,w,h,r=0):p.drawRoundedRect(QRectF(x,y,w,h),r,r)
    def circle(x,y,r):p.drawEllipse(QPointF(x,y),r,r)
    def polygon(points):p.drawPolygon(QPolygonF([QPointF(x,y) for x,y in points]))
    if index==0:
        circle(256,224,132);line(256,224,256,133);line(256,224,323,260)
        for y,w in [(395,140),(428,105)]:line(256-w,y,256+w,y)
    elif index==1:
        for i in range(3):
            x=80+i*126;rect(x,125,100,268,7);line(x+23,165,x+77,165);line(x+25,250,x+44,269);line(x+44,269,x+80,226)
    elif index==2:
        polygon([(100,390),(100,105),(392,390)])
        for y in range(145,355,42):line(100,y,125 if y%2 else 142,y)
        line(168,390,168,365);line(230,390,230,365);line(292,390,292,365)
    elif index==3:
        for y in range(90,435,58):
            p.setOpacity(.18);line(65,y,450,y)
        p.setOpacity(1)
        path=QPainterPath(QPointF(60,285))
        for x,y in [(128,285),(165,155),(213,385),(275,100),(330,285),(448,285)]:path.lineTo(x,y)
        p.drawPath(path)
    elif index==4:
        circle(256,260,154);circle(256,260,120);line(65,100,65,410);line(95,100,95,205);line(125,100,125,205);line(65,205,125,205);line(443,100,443,410)
    elif index==5:
        rect(82,115,348,305,18);line(82,190,430,190);line(165,85,165,145);line(350,85,350,145)
        for x in [150,250,350]:
            for y in [255,345]:rect(x-20,y-20,40,40,8)
    elif index==6:
        p.setBrush(QColor('#fff8e9'));p.setPen(Qt.PenStyle.NoPen);polygon([(125,65),(387,65),(387,448),(360,428),(335,448),(310,428),(285,448),(260,428),(235,448),(210,428),(185,448),(155,428),(125,448)])
        p.setPen(QPen(QColor('#244749'),13));line(172,145,340,145);line(172,220,265,220);line(172,280,330,280);line(172,345,300,345)
    elif index==7:
        for radius in [70,118,170]:circle(256,256,radius)
        p.setBrush(QColor(accent));circle(256,256,20)
    elif index==8:
        for i,color in enumerate(['#c44081','#e9ba58','#275f84','#80b9a3','#b28ed2']):
            angle=i*math.tau/5;p.setBrush(QColor(color));p.setPen(Qt.PenStyle.NoPen);circle(256+105*math.cos(angle),256+105*math.sin(angle),70)
    elif index==9:
        polygon([(252,72),(285,205),(420,245),(286,280),(252,420),(218,281),(80,245),(218,208)])
        circle(392,105,18);line(125,365,170,410)
    elif index==10:
        for x,h in [(105,130),(225,250),(345,185)]:rect(x,410-h,70,h,14)
        line(75,432,440,432)
    elif index==11:
        rect(155,162,200,230,18);circle(255,138,54);line(125,392,385,392)
        p.setBrush(QColor(accent));polygon([(255,205),(285,278),(255,335),(225,278)])
    elif index==12:
        for i,h in enumerate([100,220,315,180,260,125]):rect(70+i*65,420-h,35,h,13)
    elif index==13:
        rect(75,95,365,295);line(255,390,255,445);line(170,445,340,445)
        line(135,185,280,185);line(135,240,365,240);line(135,295,320,295)
    elif index==14:
        path=QPainterPath(QPointF(256,420));path.cubicTo(70,340,85,165,250,85);path.cubicTo(415,165,430,340,256,420);p.drawPath(path)
        line(256,410,256,150);line(256,295,175,225);line(256,340,337,275)
    elif index==15:
        for x in [110,400]:
            for y in [110,400]:polygon([(x,y-25),(x+25,y),(x,y+25),(x-25,y)])
        p.setBrush(QColor(accent));polygon([(256,135),(280,220),(365,255),(280,282),(256,365),(229,280),(145,255),(229,228)])
    elif index==16:
        for x,y in [(160,190),(310,155),(270,320)]:circle(x,y,75);line(x,y-72,x+30,y-105)
        line(80,425,425,425)
    elif index==17:
        for x in range(100,420,100):
            for y in range(100,420,100):
                p.setBrush(QColor(accent) if (x//100+y//100)%2==0 else Qt.BrushStyle.NoBrush);rect(x-28,y-28,56,56,8)
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif index==18:
        polygon([(256,70),(440,256),(256,440),(70,256)]);circle(256,256,83)
        for x,y in [(256,70),(440,256),(256,440),(70,256)]:circle(x,y,25)
    else:
        for y in [180,275,370]:
            path=QPainterPath(QPointF(65,y));path.cubicTo(150,y-55,200,y+55,280,y);path.cubicTo(340,y-40,390,y+40,450,y);p.drawPath(path)
        polygon([(195,220),(315,220),(285,260),(225,260)]);line(256,115,256,210);polygon([(265,120),(325,198),(265,198)])
    p.end();Path(destination).parent.mkdir(parents=True,exist_ok=True)
    if not image.save(str(destination),'PNG'):raise RuntimeError('Could not save original sample icon.')
