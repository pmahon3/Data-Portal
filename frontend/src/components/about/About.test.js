import { render, screen } from '@testing-library/react';
import About from './About';

// Minimal working example for react-scripts test
test('renders About component with heading', () => {
  render(<About />);
  const headingElement = screen.getByText(/About INN Project/i);
  expect(headingElement).toBeInTheDocument();
});

test('renders About component with description text', () => {
  render(<About />);
  const descriptionElement = screen.getByText(/SFU's Institute for Neuroscience/i);
  expect(descriptionElement).toBeInTheDocument();
});

