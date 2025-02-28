use glob::glob;
use heck::ToSnakeCase;
use proc_macro2::TokenStream;
use quote::quote;
use std::{env, error::Error, fs, path::Path};
use syn::{File, Item, Lit, Meta, NestedMeta};

fn main() -> Result<(), Box<dyn Error>> {
    let pattern = "src/features/*.rs";
    let mut field_tokens: Vec<TokenStream> = Vec::new();

    for entry in glob(pattern)? {
        let path = entry?;
        let content = fs::read_to_string(&path)?;
        let syntax: File = syn::parse_file(&content)?;

        let module_name = path.file_stem().unwrap().to_str().unwrap();
        let mod_ident = syn::Ident::new(module_name, proc_macro2::Span::call_site());

        for item in syntax.items {
            if let Item::Struct(item_struct) = item {
                let struct_ident = &item_struct.ident;

                if !matches!(item_struct.vis, syn::Visibility::Public(_))
                    || !struct_ident.to_string().ends_with("Config")
                {
                    continue;
                }

                let mut serde_rename: Option<String> = None;
                for attr in &item_struct.attrs {
                    if attr.path.is_ident("serde") {
                        if let Ok(meta) = attr.parse_meta() {
                            if let Meta::List(meta_list) = meta {
                                for nested in meta_list.nested.iter() {
                                    if let NestedMeta::Meta(Meta::NameValue(nv)) = nested {
                                        if nv.path.is_ident("rename") {
                                            if let Lit::Str(lit_str) = &nv.lit {
                                                serde_rename = Some(lit_str.value());
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                if let Some(rename_value) = serde_rename {
                    // Convert the rename value to snake_case for the field name.
                    let field_name_str = rename_value.to_snake_case();
                    let field_ident = syn::Ident::new(&field_name_str, struct_ident.span());
                    let type_path = quote! { crate::features::#mod_ident::#struct_ident };
                    let tokens = quote! {
                        #[serde(rename = #rename_value)]
                        pub #field_ident: #type_path,
                    };
                    field_tokens.push(tokens);
                }
            }
        }
    }

    let output = quote! {
        use serde::{Serialize, Deserialize};
        use typed_builder::TypedBuilder;

        #[derive(Clone, Serialize, Deserialize, TypedBuilder)]
        pub struct Values {
            #(#field_tokens)*
        }
    };

    let out_dir = env::var("OUT_DIR")?;
    let dest_path = Path::new(&out_dir).join("values.rs");
    fs::write(&dest_path, output.to_string())?;

    println!("cargo:rerun-if-changed=src/features/");
    Ok(())
}
