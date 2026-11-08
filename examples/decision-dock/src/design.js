import React from 'react';
import {View,Text} from 'react-native';
import {useScale} from './ui';

// Original code-drawn illustrations; no external artwork, icon font or network.
export function Orbit({color='#f5bb69',size=180,kind='sun',value=0}){
 const s=useScale(),n=size*s;
 return <View accessible={false} style={{width:n,height:n,alignItems:'center',justifyContent:'center'}}>
  {[0,1,2].map(i=><View key={i} style={{position:'absolute',width:n*(1-i*.19),height:n*(1-i*.19),borderWidth:Math.max(1,s*2),borderColor:color,opacity:.18+i*.13,borderRadius:n,transform:[{rotate:(i*30)+'deg'}]}}/>)}
  {kind==='sun'?Array.from({length:12},(_,i)=><View key={i} style={{position:'absolute',width:3*s,height:15*s,backgroundColor:color,transform:[{rotate:(i*30)+'deg'},{translateY:-n*.4}]}}/>):null}
  <View style={{width:n*.5,height:n*.5,borderRadius:kind==='gem'?12*s:n,borderWidth:Math.max(1,3*s),borderColor:color,backgroundColor:kind==='sun'?color:'transparent',transform:[{rotate:kind==='gem'?'45deg':'0deg'}]}}/>
  {kind==='clock'?<View style={{position:'absolute',width:4*s,height:n*.29,backgroundColor:color,transform:[{translateY:-n*.1},{rotate:(value*6)+'deg'}]}}/>:null}
 </View>;
}
export function Columns({children,gap=22}){const s=useScale();return <View style={{flexDirection:'row',gap:gap*s,alignItems:'flex-start',flexWrap:'wrap'}}>{children}</View>;}
export function Panel({children,grow=1,width,style={}}){const s=useScale();return <View style={{flex:width?undefined:grow,width:width?width*s:undefined,minWidth:140*s,...style}}>{children}</View>;}
export function Rule({color='#cf8752',vertical=false}){const s=useScale();return <View style={{backgroundColor:color,opacity:.5,...(vertical?{width:2*s,alignSelf:'stretch'}:{height:2*s,marginVertical:14*s})}}/>;}
export function Meter({value=0,color='#cf8752',height=9}){const s=useScale();return <View style={{height:height*s,backgroundColor:'#77777730',overflow:'hidden',borderRadius:height*s,marginVertical:10*s}}><View style={{width:Math.max(0,Math.min(100,value*100))+'%',height:'100%',backgroundColor:color}}/></View>;}
export function Label({children,color='#938880',size=13}){const s=useScale();return <Text style={{color,fontSize:size*s,letterSpacing:2*s,marginVertical:5*s}}>{children}</Text>;}
export function Number({children,color='#cf8752',size=70}){const s=useScale();return <Text style={{color,fontSize:size*s,fontWeight:'bold',fontVariant:['tabular-nums']}}>{children}</Text>;}
export function Skyline({color='#cf8752'}){const s=useScale();return <View accessible={false} style={{height:58*s,flexDirection:'row',alignItems:'flex-end',gap:5*s,marginTop:10*s}}>{[12,23,18,42,28,53,33,21,43,27,16,36,24,14].map((h,i)=><View key={i} style={{width:16*s,height:h*s,backgroundColor:color,opacity:.15+(i%3)*.15,borderTopLeftRadius:5*s}}/>)}</View>;}
