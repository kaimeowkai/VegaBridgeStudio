"""Built as a separate one-file worker so no installed application file is locked."""
from vegabridge.update_apply import main

if __name__=='__main__':
    raise SystemExit(main())
