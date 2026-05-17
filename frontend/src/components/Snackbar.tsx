import './Snackbar.css'

type SnackbarProps = {
    text: string,
    color: string
}

export function Snackbar({ text, color }: SnackbarProps) {
    return (
        text
        ? <div className={`snackbar bg-${color} rounded-lg show`}>{text}</div>
        : null
    )
}