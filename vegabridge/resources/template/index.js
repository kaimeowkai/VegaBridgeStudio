import React, {useState} from 'react';
import {AppRegistry, View, Text, Pressable, StyleSheet, useWindowDimensions} from 'react-native';

function App() {
  const [count, setCount] = useState(0);
  const {width, height} = useWindowDimensions();
  const scale = Math.min(1, width / 1280, height / 720);

  return (
    <View style={[styles.page, {padding: 90 * scale}]}>
      <Text style={[styles.title, {fontSize: 52 * scale}]}>Hello from Windows</Text>
      <Text style={[styles.subtitle, {fontSize: 28 * scale, marginTop: 24 * scale}]}>
        Built with VegaBridge Studio. Running on Amazon Vega.
      </Text>
      <Pressable
        hasTVPreferredFocus
        onPress={() => setCount(value => value + 1)}
        style={({focused}) => [styles.button, {marginTop: 40 * scale, padding: 22 * scale}, focused && styles.focused]}>
        <Text style={[styles.counter, {fontSize: 28 * scale}]}>Remote button presses: {count}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: '#071624', padding: 90, justifyContent: 'center'},
  title: {color: '#5eead4', fontSize: 52, fontWeight: 'bold'},
  subtitle: {color: '#ffffff', fontSize: 28, marginTop: 24},
  button: {marginTop: 40, padding: 22, backgroundColor: '#14354a', borderRadius: 10},
  focused: {backgroundColor: '#0e7490'},
  counter: {color: '#ffffff', fontSize: 28},
});

AppRegistry.registerComponent('com.brutalgamestudios.windowsnativehello.main', () => App);
