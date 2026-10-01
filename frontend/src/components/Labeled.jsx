// Visible caption above a form control, so a field stays identifiable
// after its placeholder/selected text is replaced.
export default function Labeled({ label, className = "", children }) {
  return (
    <label className={`block ${className}`}>
      <span className="label-eyebrow block mb-1">{label}</span>
      {children}
    </label>
  );
}
