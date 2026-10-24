export function SectionHeading({ title, subtitle, action }) {
  return <div className="section-heading"><div><h1>{title}</h1><p>{subtitle}</p></div>{action && <div className="heading-action">{action}</div>}</div>;
}
