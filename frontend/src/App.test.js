// Minimal working example for react-scripts test
// This file demonstrates a basic test setup
// For a simpler example, see src/components/about/About.test.js

import { render, screen } from '@testing-library/react';

// Simple utility function test example
function add(a, b) {
  return a + b;
}

test('adds two numbers correctly', () => {
  expect(add(2, 3)).toBe(5);
  expect(add(-1, 1)).toBe(0);
});

// Simple component test example
function HelloWorld() {
  return <div>Hello, World!</div>;
}

test('renders HelloWorld component', () => {
  render(<HelloWorld />);
  const element = screen.getByText(/Hello, World!/i);
  expect(element).toBeInTheDocument();
});
